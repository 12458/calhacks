from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding
import spec_pb2
import uuid
import time
import base64
import threading
import os
import random
from skylo import SerialWrapper
from rylr998 import RYLR998

NODE_ID = "FIXED170"  # Generate a UUID4 for the node ID
AES_KEY = b'password'.ljust(16, b'\0')[:16]  # Ensure the key is 16 bytes

serial_port = '/dev/ttyUSB0'  # Replace with your serial port
wrapper = SerialWrapper(serial_port, baudrate=115200, timeout=1)
wrapper.mqtt_config(connection_id=1, client_name="testclient_12458_sk", broker_url="test.mosquitto.org")
wrapper.mqtt_connect(1)

# Set to keep track of received packet UUIDs
received_packets = set()
# Dictionary to keep track of sent packets and their acknowledgment status
acknowledgments = {}
# Set to keep track of discovered nodes
discovered_nodes = set()

#
def aes_encrypt(message):
    if isinstance(message, str):
        message = message.encode()

    # Generate a random 16-byte IV for CBC mode
    iv = os.urandom(16)

    # Create AES cipher with the key and IV in CBC mode
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    # Add padding to the message (AES requires the input to be a multiple of the block size)
    padder = sym_padding.PKCS7(algorithms.AES.block_size).padder()
    padded_message = padder.update(message) + padder.finalize()

    # Encrypt the message
    encrypted_message = encryptor.update(padded_message) + encryptor.finalize()

    # Return the IV and the encrypted message
    return iv + encrypted_message

def aes_decrypt(ciphertext):
    # Extract the IV (first 16 bytes) and the actual encrypted message
    iv = ciphertext[:16]
    encrypted_message = ciphertext[16:]

    # Create AES cipher with the key and IV in CBC mode
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()

    # Decrypt the message
    decrypted_padded_message = decryptor.update(encrypted_message) + decryptor.finalize()

    # Remove padding from the decrypted message
    unpadder = sym_padding.PKCS7(algorithms.AES.block_size).unpadder()
    decrypted_message = unpadder.update(decrypted_padded_message) + unpadder.finalize()

    return decrypted_message.decode()


def initialize_lora(address, network_id):
    # Initialize the LoRa module
    lora = RYLR998(port='/dev/ttyAMA0')
    lora.set_address(address)  # Set this node's address
    lora.set_network_id(network_id)  # Set the network ID
    lora.set_rf_parameters(11,9,4,12)
    lora.set_band(902687500)

    return lora

# AES Encryption and Decryption functions remain unchanged

def send_message(lora, destination, message_content):
    # Encrypt the message
    encrypted_message = aes_encrypt(message_content.encode())

    # Create a NetworkMessage
    network_message = spec_pb2.NetworkMessage()
    network_message.node_id = NODE_ID
    network_message.timestamp = int(time.time())
    network_message.message_content = encrypted_message
    network_message.destination = destination

    # Create a Packet and assign the NetworkMessage to it
    packet = spec_pb2.Packet()
    packet.packet_uuid = uuid.uuid4().hex[:8]  # Generate a UUID4 for the packet
    packet.packet_type = spec_pb2.NETWORK_MESSAGE
    packet.network_message.CopyFrom(network_message)

    # Serialize and send the packet
    send_packet(lora, packet)

    # Add the packet to the acknowledgment dictionarya
    acknowledgments[packet.packet_uuid] = False

def send_packet(lora, packet):
    serialized_packet = packet.SerializeToString()
    b64_packet = base64.urlsafe_b64encode(serialized_packet)
    lora.send_data(0, str(b64_packet.decode()))
    print(f"Sent packet: {b64_packet} / {packet}")

def listen_for_data(lora):
    print("Listening for incoming data...")
    while True:
        incoming_data = lora.receive_data()
        if incoming_data:
            print(f"Received raw data: {incoming_data}")
            data_parts = incoming_data.split(",")
            if len(data_parts) >= 3:
                encoded_packet = data_parts[2]
                serialized_packet = base64.urlsafe_b64decode(encoded_packet)
                received_packet = spec_pb2.Packet()
                received_packet.ParseFromString(serialized_packet)

                if received_packet.packet_uuid in received_packets:
                    print(f"Duplicate packet {received_packet.packet_uuid} received, skipping processing.")
                    continue

                received_packets.add(received_packet.packet_uuid)
                print(f"Received Packet: {received_packet}")

                if received_packet.packet_type == spec_pb2.NETWORK_MESSAGE:
                    process_network_message(lora, received_packet)
                elif received_packet.packet_type == spec_pb2.ACK_MESSAGE:
                    process_ack_message(received_packet)
                elif received_packet.packet_type == spec_pb2.DISCOVER_MESSAGE:
                    process_discover_message(lora, received_packet)
                elif received_packet.packet_type == spec_pb2.ANNOUNCE_MESSAGE:
                    process_announce_message(lora, received_packet)

def process_network_message(lora, received_packet):
    if received_packet.network_message.destination != NODE_ID and not received_packet.network_message.destination.startswith("+"):
        # Retransmit the packet if it's not for us
        print(f"Retransmitting packet {received_packet.packet_uuid}")
        #send_packet(lora, received_packet)
    else:
        # Process the message if it's for us or it's a relay SMS
        decrypted_message = aes_decrypt(received_packet.network_message.message_content)
        print(f"Decrypted message: {decrypted_message}")
        send_ack(lora, received_packet)
        
        if received_packet.network_message.destination.startswith("+"):
            print(f"Received relay SMS: {decrypted_message}")
            # Relay to MQTT
            wrapper.mqtt_publish(1, "12458Test/pub", base64.urlsafe_b64encode(received_packet.SerializeToString()).decode())

def process_ack_message(received_packet):
    message_id = received_packet.ack_message.message_id
    if message_id in acknowledgments:
        acknowledgments[message_id] = True
        print(f"ACK received for packet UUID: {message_id}")

def process_discover_message(lora, received_packet):
    print("Received DISCOVER message. Announcing our presence.")
    time.sleep(random.randint(1,10)/10)
    send_announce_message(lora)
    # Retransmit the DISCOVER message
    #send_packet(lora, received_packet)

def process_announce_message(lora, received_packet):
    announced_node_id = received_packet.announce_message.node_id
    if announced_node_id not in discovered_nodes:
        discovered_nodes.add(announced_node_id)
        print(f"Discovered new node: {announced_node_id}")
    # Retransmit the ANNOUNCE message
    #send_packet(lora, received_packet)

def send_ack(lora, received_packet):
    ack_message = spec_pb2.AckMessage()
    ack_message.message_id = received_packet.packet_uuid
    ack_message.node_id = NODE_ID
    ack_message.timestamp = int(time.time())

    ack_packet = spec_pb2.Packet()
    ack_packet.packet_uuid = uuid.uuid4().hex[:8]
    ack_packet.packet_type = spec_pb2.ACK_MESSAGE
    ack_packet.ack_message.CopyFrom(ack_message)

    send_packet(lora, ack_packet)

def send_discover_message(lora):
    discover_message = spec_pb2.DiscoverMessage()
    discover_message.timestamp = int(time.time())

    packet = spec_pb2.Packet()
    packet.packet_uuid = uuid.uuid4().hex[:8]
    packet.packet_type = spec_pb2.DISCOVER_MESSAGE
    packet.discover_message.CopyFrom(discover_message)

    send_packet(lora, packet)
    print("Sent DISCOVER message")

def send_announce_message(lora):
    announce_message = spec_pb2.AnnounceMessage()
    announce_message.node_id = NODE_ID
    announce_message.timestamp = int(time.time())

    packet = spec_pb2.Packet()
    packet.packet_uuid = uuid.uuid4().hex[:8]
    packet.packet_type = spec_pb2.ANNOUNCE_MESSAGE
    packet.announce_message.CopyFrom(announce_message)

    send_packet(lora, packet)
    print(f"Sent ANNOUNCE message for node {NODE_ID}")


def listen_for_mqtt():
    print("Listening for MQTT messages on 12458Test/sub...")
    wrapper.mqtt_subscribe(1, "12458Test/sub")
    while True:
        mqtt_data = wrapper.mqtt_receive_message()
        if mqtt_data and "%MQTTEVU:\"PUBRCV\"" in mqtt_data:
            try:
                # Extract the payload from the MQTT message
                _, _, _, topic, length = mqtt_data.split(',')
                payload = wrapper.read_response()
                
                # Decode the base64 payload
                decoded_payload = base64.urlsafe_b64decode(payload)
                
                # Parse the payload into a Packet object
                mqtt_packet = spec_pb2.Packet()
                mqtt_packet.ParseFromString(decoded_payload)
                print(f"Received MQTT packet: {mqtt_packet}")
                
                # Transmit the packet over LoRa
                send_packet(lora, mqtt_packet)
                print(f"Transmitted MQTT packet over LoRa: {mqtt_packet.packet_uuid}")
                time.sleep(1)
            except Exception as e:
                print(f"Error processing MQTT message: {e}")

def process_network_message(lora, received_packet):
    if received_packet.network_message.destination != NODE_ID and not received_packet.network_message.destination.startswith("+"):
        # Retransmit the packet if it's not for us
        print(f"Retransmitting packet {received_packet.packet_uuid}")
        #send_packet(lora, received_packet)
    else:
        # Process the message if it's for us or it's a relay SMS
        decrypted_message = aes_decrypt(received_packet.network_message.message_content)
        print(f"Decrypted message: {decrypted_message}")
        send_ack(lora, received_packet)
        
        if received_packet.network_message.destination.startswith("+"):
            print(f"Received relay SMS: {decrypted_message}")
            # Relay to MQTT
            wrapper.mqtt_publish(1, "12458Test/pub", base64.urlsafe_b64encode(received_packet.SerializeToString()).decode())

def main():
    global lora
    lora = initialize_lora(address=3, network_id=18)

    listen_thread = threading.Thread(target=listen_for_data, args=(lora,))
    listen_thread.daemon = True
    listen_thread.start()

    mqtt_thread = threading.Thread(target=listen_for_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    try:
        while True:
            user_input = input("Enter message, 'exit' to quit, '?ACK' for ACK status, or 'DISCOVER' to find devices: ").strip()
            if user_input.lower() == 'exit':
                break
            elif user_input == '?ACK':
                for packet_uuid, acked in acknowledgments.items():
                    status = "ACKED" if acked else "PENDING"
                    print(f"Packet UUID {packet_uuid}: {status}")
            elif user_input.upper() == 'DISCOVER':
                send_discover_message(lora)
                print("Waiting for responses...")
                time.sleep(5)  # Wait for 5 seconds to collect responses
                print("Discovered nodes:")
                for node in discovered_nodes:
                    print(node)
            else:
                destination = input("Enter the destination node ID: ").strip()
                send_message(lora, destination, user_input)
                time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down LoRa receiver...")
    finally:
        lora.close()
        wrapper.mqtt_disconnect(1)
        wrapper.close_connection()

if __name__ == "__main__":
    print(f"Node ID: {NODE_ID}")
    main()