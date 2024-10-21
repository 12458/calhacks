from rylr998 import RYLR998
import spec_pb2
import uuid
import time
import base64

# Generate a UUID4 for the node ID
NODE_ID = uuid.uuid4().hex

# Create a NetworkMessage
network_message = spec_pb2.NetworkMessage()
network_message.node_id = NODE_ID
network_message.timestamp = int(time.time())
network_message.message_content = "Hello, this is a test message!".encode()
network_message.destination = "node-456"

# Create a Packet and assign the NetworkMessage to it
packet = spec_pb2.Packet()
packet.packet_uuid = str(uuid.uuid4())  # Generate a UUID4 for the packet
packet.packet_type = spec_pb2.NETWORK_MESSAGE
packet.network_message.CopyFrom(network_message)  # Add the NetworkMessage

# Serialize the Packet to a binary format (to send over the network)
serialized_packet = packet.SerializeToString()

# base64 encode the serialized packet
b64_packet = base64.b64encode(serialized_packet)


lora = RYLR998(port='/dev/ttyAMA0')
lora.set_address(120)
lora.set_network_id(18)
lora.send_data(0, str(b64_packet.decode()))
print(f"Sent data: {b64_packet} / {packet}")
#wait for ack, when received deserialize and print
while (x := lora.receive_data()) is None:
    print("Waiting for data...")
    time.sleep(1)
    lora.send_data(0, str(b64_packet.decode()))
    print("Retransmitting")
print(x)
# Deserialize the received data
received_packet = spec_pb2.Packet()
received_packet.ParseFromString(base64.b64decode(x.split(",")[2]))
print(received_packet)
lora.close()