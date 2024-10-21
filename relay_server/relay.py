import paho.mqtt.client as mqtt
import base64
from twilio.rest import Client
from spec_pb2 import Packet, PacketType, NetworkMessage
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
import os
import uuid
import time

import google.generativeai as genai
import os

genai.configure(api_key="YOUR_API_KEY")
model = genai.GenerativeModel("gemini-1.5-pro")
chat = model.start_chat(history=[])

# Define Twilio API credentials
TWILIO_ACCOUNT_SID = 'YOUR_API_KEY'
TWILIO_AUTH_TOKEN = 'YOUR_API_KEY'
TWILIO_PHONE_NUMBER = 'YOUR_PHONE_NUMBER'

# AES key for encryption/decryption (must be 16, 24, or 32 bytes for AES-128/192/256)
AES_KEY = b'password'.ljust(16, b'\0')[:16]  # Ensure the key is 16 bytes

def aes_encrypt(message):
    if isinstance(message, str):
        message = message.encode()

    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    padder = sym_padding.PKCS7(algorithms.AES.block_size).padder()
    padded_message = padder.update(message) + padder.finalize()

    encrypted_message = encryptor.update(padded_message) + encryptor.finalize()

    return iv + encrypted_message

def aes_decrypt(ciphertext):
    encrypted_data = ciphertext
    iv = encrypted_data[:16]
    encrypted_message = encrypted_data[16:]
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_padded_message = decryptor.update(encrypted_message) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(algorithms.AES.block_size).unpadder()
    decrypted_message = unpadder.update(decrypted_padded_message) + unpadder.finalize()
    return decrypted_message.decode()

def perform_gemini_search(query):
    print(f"Performing Gemini search for: {query}")
    response = chat.send_message(query)
    print(f"Received response: {response.text}")
    return response.text

def split_message(message, chunk_size=45):
    return [message[i:i+chunk_size] for i in range(0, len(message), chunk_size)]

def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    client.subscribe("12458Test/pub")

def on_message(client, userdata, msg):
    print(msg.topic + " " + str(msg.payload))
    msg_decoded = base64.urlsafe_b64decode(msg.payload)

    try:
        packet = Packet()
        packet.ParseFromString(msg_decoded)
    except Exception as e:
        print(f"Failed to parse packet: {e}")
        return

    if packet.packet_type == PacketType.NETWORK_MESSAGE:
        network_message = packet.network_message
        try:
            decrypted_message = aes_decrypt(network_message.message_content)
            print(f"Decrypted message: {decrypted_message}")

            if network_message.destination.startswith("+Q"):
                query = decrypted_message.strip()  # Remove "+QUESTION" and leading/trailing spaces
                search_result = perform_gemini_search(query)

                chunks = split_message(search_result)


                # Send each chunk back via MQTT
                for i, chunk in enumerate(chunks):
                    encrypted_result = aes_encrypt(chunk)
                    response_packet = Packet()
                    response_packet.packet_uuid = uuid.uuid4().hex[:8]
                    response_packet.packet_type = PacketType.NETWORK_MESSAGE

                    response_network_message = NetworkMessage()
                    response_network_message.node_id = "Server"
                    response_network_message.timestamp = int(time.time())
                    response_network_message.message_content = encrypted_result
                    response_network_message.destination = network_message.node_id

                    response_packet.network_message.CopyFrom(response_network_message)

                    serialized_packet = response_packet.SerializeToString()
                    encoded_packet = base64.urlsafe_b64encode(serialized_packet)

                    client.publish("12458Test/sub", encoded_packet)
                    print(f"Sent chunk {i+1} (size {len(serialized_packet)})/{len(chunks)}")
            else:
                send_sms(network_message.destination, decrypted_message)
        except Exception as e:
            print(f"Failed to process message: {e}")

def send_sms(destination, message_content):
    print(f"Sending message to {destination}: {message_content}")
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message_content,
            from_=TWILIO_PHONE_NUMBER,
            to=destination
        )
        print(f"Message sent to {destination}: {message.sid}")
    except Exception as e:
        print(f"Failed to send message: {e}")

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect("test.mosquitto.org", 1883, 60)
mqtt_client.loop_forever()