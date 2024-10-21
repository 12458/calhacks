import serial
import time

class SerialWrapper:
    def __init__(self, port, baudrate=115200, timeout=1):
        """
        Initialize the serial connection.
        
        :param port: Serial port to use (e.g., 'COM3', '/dev/ttyUSB0')
        :param baudrate: Baud rate for the serial communication (default is 115200)
        :param timeout: Timeout for read/write operations (default is 1 second)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        
        # Initialize the connection
        self.open_connection()

    def open_connection(self):
        """
        Open the serial connection.
        """
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            if self.serial_conn.is_open:
                print(f"Connected to {self.port} at {self.baudrate} baudrate.")
        except serial.SerialException as e:
            print(f"Error opening the serial connection: {e}")
            self.serial_conn = None

    def close_connection(self):
        """
        Close the serial connection.
        """
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print(f"Connection to {self.port} closed.")

    def send_command(self, command, wait_for_response=True):
        """
        Send a command to the serial device.
        
        :param command: The AT command to send.
        :param wait_for_response: Whether to wait for and return the response.
        :return: Response from the device, or None if wait_for_response is False.
        """
        if self.serial_conn is None:
            raise ConnectionError("Serial connection is not open.")

        try:
            # Send the command followed by a carriage return
            full_command = command + '\r'
            self.serial_conn.write(full_command.encode())
            time.sleep(0.1)  # Small delay after sending the command
            
            if wait_for_response:
                return self.read_response()
            return None

        except serial.SerialTimeoutException:
            print("Error: Write timeout occurred.")
        except serial.SerialException as e:
            print(f"Serial communication error: {e}")

    def read_response(self):
        """
        Read the response from the serial device.
        
        :return: The response from the device as a string.
        """
        if self.serial_conn is None:
            raise ConnectionError("Serial connection is not open.")
        
        try:
            response = self.serial_conn.read_until(b'\r\n').decode('utf-8').strip()
            return response
        except serial.SerialException as e:
            print(f"Error reading from the serial device: {e}")
            return None

    def flush(self):
        """
        Flush input and output buffers.
        """
        if self.serial_conn:
            self.serial_conn.reset_input_buffer()
            self.serial_conn.reset_output_buffer()

    def send_at_command(self, command):
        """
        Helper function to send an AT command and return the response.
        
        :param command: The AT command to send.
        :return: The response from the device.
        """
        print(f"Sending AT command: {command}")
        response = self.send_command(command)
        print(f"Response: {response}")
        return response

    ### MQTT Commands ###
    
    def mqtt_config(self, connection_id, client_name, broker_url, port=1883, ip_type=0, keep_alive=1200, clean_session=1):
        """
        Configure MQTT connection parameters.
        
        :param connection_id: MQTT connection ID.
        :param client_name: Client identifier for MQTT.
        :param broker_url: MQTT broker URL.
        :param port: MQTT broker port (default is 1883).
        :param ip_type: Preferred IP type (0 for IPv4).
        :param keep_alive: Keep-alive time in seconds (default is 1200).
        :param clean_session: 1 for clean session (default is 1).
        """
        # Clear existing configuration
        self.send_at_command(f'AT%MQTTCFG="clear",{connection_id}')
        
        # Set client name and broker URL
        self.send_at_command(f'AT%MQTTCFG="nodes",{connection_id},"{client_name}","{broker_url}"')
        
        # Set IP type and port
        self.send_at_command(f'AT%MQTTCFG="IP",{connection_id},,{ip_type},{port}')
        
        # Set protocol, keep-alive, and clean session
        self.send_at_command(f'AT%MQTTCFG="PROTOCOL",{connection_id},0,{keep_alive},{clean_session}')
        
        # Enable all MQTT events
        self.send_at_command(f'AT%MQTTEV="all",{connection_id}')

    def mqtt_connect(self, connection_id):
        """
        Connect to the MQTT broker.
        
        :param connection_id: MQTT connection ID.
        :return: The connection confirmation status.
        """
        response = self.send_at_command(f'AT%MQTTCMD="connect",{connection_id}')
        if "%MQTTEVU:\"CONCONF\"" in response:
            print("Connected to MQTT broker successfully.")
        return response

    def mqtt_disconnect(self, connection_id):
        """
        Disconnect from the MQTT broker.
        
        :param connection_id: MQTT connection ID.
        :return: The disconnect confirmation status.
        """
        response = self.send_at_command(f'AT%MQTTCMD="disconnect",{connection_id}')
        if "%MQTTEVU:\"DISCONF\"" in response:
            print("Disconnected from MQTT broker.")
        return response

    def mqtt_subscribe(self, connection_id, topic, qos=0):
        """
        Subscribe to a topic on the MQTT broker.
        
        :param connection_id: MQTT connection ID.
        :param topic: The topic to subscribe to.
        :param qos: Quality of Service (QoS) level (default is 0).
        :return: Subscription confirmation status.
        """
        response = self.send_at_command(f'AT%MQTTCMD="subscribe",{connection_id},{qos},"{topic}"')
        return response

    def mqtt_unsubscribe(self, connection_id, topic):
        """
        Unsubscribe from a topic on the MQTT broker.
        
        :param connection_id: MQTT connection ID.
        :param topic: The topic to unsubscribe from.
        :return: Unsubscribe confirmation status.
        """
        response = self.send_at_command(f'AT%MQTTCMD="unsubscribe",{connection_id},"{topic}"')
        return response

    def mqtt_publish(self, connection_id, topic, message, qos=0):
        """
        Publish a message to a topic on the MQTT broker.
        
        :param connection_id: MQTT connection ID.
        :param topic: The topic to publish to.
        :param message: The message content.
        :param qos: Quality of Service (QoS) level (default is 0).
        :return: Publish confirmation status.
        """
        response = self.send_at_command(f'AT%MQTTCMD="publish",{connection_id},{qos},0,"{topic}",{len(message)}\r{message}')
        return response

    def mqtt_receive_message(self):
        """
        Listen for incoming messages from the subscribed topics.
        
        :return: Received message details.
        """
        response = self.read_response()
        if "%MQTTEVU:\"PUBRCV\"" in response:
            print(f"Message received: {response}")
        return response

# Example usage
if __name__ == "__main__":
    serial_port = '/dev/ttyUSB0'  # Replace with your serial port
    wrapper = SerialWrapper(serial_port, baudrate=115200, timeout=1)
    
    try:
        # Example: Configuring and connecting to an MQTT broker
        wrapper.mqtt_config(connection_id=1, client_name="testclient_12458_sk", broker_url="test.mosquitto.org")
        wrapper.mqtt_connect(1)
        
        # Example: Subscribing and publishing to a topic
        wrapper.mqtt_subscribe(1, "12458Test/sub", qos=0)
        wrapper.mqtt_publish(1, "12458Test/pub", "Hello MQTT")
        
        # Receive an incoming message
        wrapper.flush()
        while True:
            msg = wrapper.mqtt_receive_message()
            if "%MQTTEVU:\"PUBRCV\"" in msg:
                msg = wrapper.mqtt_receive_message()
                print(f"Received message: {msg}")
                break
        
        # Unsubscribe and disconnect
        wrapper.mqtt_unsubscribe(1, "12458Test")
        wrapper.mqtt_disconnect(1)
        
    finally:
        wrapper.close_connection()
