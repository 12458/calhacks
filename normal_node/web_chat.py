from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import time
import chat as lora_chat  # Import the modified LoRa chat module

app = Flask(__name__)
socketio = SocketIO(app)

lora = None
messages = []

@app.route('/')
def index():
    return render_template('index.html', node_id=lora_chat.get_node_id())

@socketio.on('send_message')
def handle_message(data):
    destination = data['destination']
    content = data['content']
    result = lora_chat.send_message(lora, destination, content)
    messages.append(result)
    emit('new_message', result)

@socketio.on('discover')
def handle_discover():
    result = lora_chat.send_discover_message(lora)
    emit('discover_sent', result)
    time.sleep(5)  # Wait for responses
    discovered = lora_chat.get_discovered_nodes()
    emit('discovered_nodes', discovered)

@app.route('/messages')
def get_messages():
    return jsonify(messages)

@app.route('/acks')
def get_acks():
    return jsonify(lora_chat.get_acknowledgments())

def message_listener():
    while True:
        new_messages = lora_chat.listen_for_data(lora)
        if new_messages:
            for message in new_messages:
                if message is None:
                    continue
                messages.append(message)
                socketio.emit('new_message', message)
                
                if message['type'] == 'discover':
                    # If a discover message is received, update the discovered nodes
                    discovered = lora_chat.get_discovered_nodes()
                    socketio.emit('discovered_nodes', discovered)
                elif message['type'] == 'error':
                    # Emit error messages to the client
                    socketio.emit('error', {
                        'message': f"Error: {message['error']} - {message['details']}"
                    })

def initialize():
    global lora
    lora = lora_chat.initialize_lora(address=6, network_id=18)

    # Start the LoRa listener in a separate thread
    listener_thread = threading.Thread(target=message_listener)
    listener_thread.daemon = True
    listener_thread.start()

if __name__ == '__main__':
    initialize()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)