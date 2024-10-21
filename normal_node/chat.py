from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding
import spec_pb2
import uuid
import time
import os
import base64
import threading
import random
import gzip
from rylr998 import RYLR998
import binascii

NODE_ID = "FIXED178"  # Generate a UUID4 for the node ID
AES_KEY = b'password'.ljust(16, b'\0')[:16]  # Ensure the key is 16 bytes

# Set to keep track of received packet UUIDs
received_packets = set()
# Dictionary to keep track of sent packets and their acknowledgment status
acknowledgments = {}
# Set to keep track of discovered nodes
discovered_nodes = set()

def initialize_lora(address, network_id):
    # Initialize the LoRa module
    lora = RYLR998(port='/dev/ttyAMA0')
    lora.set_address(address)  # Set this node's address
    lora.set_network_id(network_id)  # Set the network ID
    lora.set_rf_parameters(11,9,4,12)
    lora.set_band(902687500)

    return lora

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

    # Serialize the Packet to a binary format
    serialized_packet = packet.SerializeToString()

    # Base64 encode the serialized packet
    b64_packet = base64.urlsafe_b64encode(serialized_packet)

    # Send the packet
    lora.send_data(0, str(b64_packet.decode()))

    # Add the packet to the acknowledgment dictionary
    acknowledgments[packet.packet_uuid] = False

    return {
        'type': 'sent',
        'packet_uuid': packet.packet_uuid,
        'destination': destination,
        'content': message_content
    }

def listen_for_data(lora):
    processed_messages = []
    received_data = lora.receive_data()
    
    if received_data:
        print(f"Processing {received_data}")
        for item in received_data:
            if isinstance(item, dict) and 'data' in item:
                try:
                    # Add padding if necessary
                    encoded_packet = item['data']
                    encoded_packet += '=' * (-len(encoded_packet) % 4)
                    # Use urlsafe_b64decode which is more forgiving
                    serialized_packet = base64.urlsafe_b64decode(encoded_packet)

                    received_packet = spec_pb2.Packet()
                    received_packet.ParseFromString(serialized_packet)

                    print(f"Received: {received_packet}")

                    if received_packet.packet_uuid in received_packets:
                        print("Skipping")
                        continue  # Skip further processing for repeated packet

                    received_packets.add(received_packet.packet_uuid)
                
                    if received_packet.packet_type == spec_pb2.NETWORK_MESSAGE:
                        result = process_network_message(lora, received_packet)
                    elif received_packet.packet_type == spec_pb2.ACK_MESSAGE:
                        result = process_ack_message(received_packet)
                    elif received_packet.packet_type == spec_pb2.DISCOVER_MESSAGE:
                        result = process_discover_message(lora, received_packet)
                    elif received_packet.packet_type == spec_pb2.ANNOUNCE_MESSAGE:
                        result = process_announce_message(lora, received_packet)
                    else:
                        result = {
                            'type': 'unknown',
                            'packet_uuid': received_packet.packet_uuid
                        }
                    
                    processed_messages.append(result)

                except (binascii.Error, base64.binascii.Error) as e:
                    print(f"Error decoding base64: {e}")
                    print(f"Problematic encoded packet: {encoded_packet}")
                    processed_messages.append({
                        'type': 'error',
                        'error': 'base64_decoding',
                        'details': str(e)
                    })
                except Exception as e:
                    print(f"Error processing packet: {e}")
                    processed_messages.append({
                        'type': 'error',
                        'error': 'packet_processing',
                        'details': str(e)
                    })
            elif isinstance(item, str):
                # Handle string responses
                processed_messages.append({
                    'type': 'other',
                    'message': item
                })
            else:
                # Handle any other unexpected data types
                processed_messages.append({
                    'type': 'unknown',
                    'message': str(item)
                })
    if processed_messages:
        print(f"processed messages: {processed_messages}")
    return processed_messages

def process_network_message(lora, received_packet):
    print(f"{received_packet.network_message.destination} != {NODE_ID}?")
    if received_packet.network_message.destination != NODE_ID:
        # Retransmit the packet if it's not for us
        #retransmit_packet(lora, base64.urlsafe_b64encode(received_packet.SerializeToString()).decode())
        return {
            'type': 'retransmitted',
            'packet_uuid': received_packet.packet_uuid
        }
    else:
        # Decrypt the message content
        decrypted_message = aes_decrypt(received_packet.network_message.message_content)

        # Construct and send an acknowledgment
        send_ack(lora, received_packet)

        return {
            'type': 'received',
            'packet_uuid': received_packet.packet_uuid,
            'from': received_packet.network_message.node_id,
            'content': decrypted_message
        }

def process_ack_message(received_packet):
    message_id = received_packet.ack_message.message_id
    if message_id in acknowledgments:
        acknowledgments[message_id] = True
        return {
            'type': 'ack',
            'packet_uuid': message_id
        }

def process_discover_message(lora, received_packet):
    time.sleep(random.randint(1,50)/10)

    send_announce_message(lora)
    # Retransmit the DISCOVER message
    # retransmit_packet(lora, base64.b64encode(received_packet.SerializeToString()).decode())
    return {
        'type': 'discover',
        'packet_uuid': received_packet.packet_uuid
    }

def process_announce_message(lora, received_packet):
    print(f"Process announce message from {received_packet.announce_message.node_id}")
    announced_node_id = received_packet.announce_message.node_id
    if announced_node_id not in discovered_nodes:
        discovered_nodes.add(announced_node_id)
    # Retransmit the ANNOUNCE message
    retransmit_packet(lora, base64.b64encode(received_packet.SerializeToString()).decode())
    return {
        'type': 'announce',
        'packet_uuid': received_packet.packet_uuid,
        'node_id': announced_node_id
    }

def send_ack(lora, received_packet):
    ack_message = spec_pb2.AckMessage()
    ack_message.message_id = received_packet.packet_uuid
    ack_message.node_id = NODE_ID
    ack_message.timestamp = int(time.time())

    ack_packet = spec_pb2.Packet()
    ack_packet.packet_uuid = uuid.uuid4().hex[:8]
    ack_packet.packet_type = spec_pb2.ACK_MESSAGE
    ack_packet.ack_message.CopyFrom(ack_message)

    serialized_ack_packet = ack_packet.SerializeToString()
    b64_ack_packet = base64.urlsafe_b64encode(serialized_ack_packet)

    lora.send_data(0, b64_ack_packet.decode())

def retransmit_packet(lora, encoded_packet):
    return
    lora.send_data(0, encoded_packet)

def send_discover_message(lora):
    discover_message = spec_pb2.DiscoverMessage()
    discover_message.timestamp = int(time.time())

    packet = spec_pb2.Packet()
    packet.packet_uuid = uuid.uuid4().hex[:8]
    packet.packet_type = spec_pb2.DISCOVER_MESSAGE
    packet.discover_message.CopyFrom(discover_message)

    serialized_packet = packet.SerializeToString()
    b64_packet = base64.urlsafe_b64encode(serialized_packet)

    lora.send_data(0, str(b64_packet.decode()))
    return {
        'type': 'discover_sent',
        'packet_uuid': packet.packet_uuid
    }

def send_announce_message(lora):
    announce_message = spec_pb2.AnnounceMessage()
    announce_message.node_id = NODE_ID
    announce_message.timestamp = int(time.time())

    packet = spec_pb2.Packet()
    packet.packet_uuid = uuid.uuid4().hex[:8]
    packet.packet_type = spec_pb2.ANNOUNCE_MESSAGE
    packet.announce_message.CopyFrom(announce_message)

    serialized_packet = packet.SerializeToString()
    b64_packet = base64.urlsafe_b64encode(serialized_packet)

    lora.send_data(0, str(b64_packet.decode()))
    return {
        'type': 'announce_sent',
        'packet_uuid': packet.packet_uuid
    }

def get_node_id():
    return NODE_ID

def get_discovered_nodes():
    return list(discovered_nodes)

def get_acknowledgments():
    return {uuid: "ACKED" if acked else "PENDING" for uuid, acked in acknowledgments.items()}

# Main loop example
def main():
    lora = initialize_lora(address=6, network_id=18)
    
    while True:
        received_data = lora.receive_data()
        if received_data:
            for item in received_data:
                if 'data' in item:
                    result = listen_for_data(lora)
                    if result:
                        print(f"Processed: {result}")
                else:
                    print(f"Other response: {item['other']}")
        
        # Here you can add other operations, like sending messages, 
        # checking for user input, etc.
        
        time.sleep(0.1)  # Short sleep to prevent CPU overuse

if __name__ == "__main__":
    main()