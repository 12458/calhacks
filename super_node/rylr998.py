import serial
import time

class RYLR998:
    def __init__(self, port, baudrate=115200, timeout=1):
        # Initialize serial connection
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        time.sleep(2)  # Allow time for the module to initialize

    def send_command(self, command):
        # Send command to LoRa module
        full_command = f"{command}\r\n"
        self.ser.write(full_command.encode())
        time.sleep(0.1)
        return self.get_response()

    def get_response(self):
        # Read the response from the module
        response = []
        while self.ser.in_waiting > 0:
            response.append(self.ser.readline().decode('utf-8').strip())
        return response if response else None

    def reset(self):
        # Reset the module
        return self.send_command("AT+RESET")

    def set_address(self, address):
        # Set the module's address (0-65535)
        return self.send_command(f"AT+ADDRESS={address}")

    def get_address(self):
        # Get the module's current address
        return self.send_command("AT+ADDRESS?")

    def get_band(self):
        return self.send_command(f"AT+BAND?")
    
    def set_band(self, band):
        return self.send_command(f"AT+BAND={band}")

    def set_network_id(self, network_id):
        # Set the LoRa network ID (3-15, 18)
        return self.send_command(f"AT+NETWORKID={network_id}")

    def get_network_id(self):
        # Get the current LoRa network ID
        return self.send_command("AT+NETWORKID?")

    def set_rf_parameters(self, spreading_factor, bandwidth, coding_rate, preamble):
        # Set the RF parameters: Spreading Factor, Bandwidth, Coding Rate, and Preamble
        return self.send_command(f"AT+PARAMETER={spreading_factor},{bandwidth},{coding_rate},{preamble}")

    def send_data(self, address, data):
        # Send data to a specific address
        length = len(data)
        cmd = f"AT+SEND={address},{length},{data}"
        print(f"Sending: {cmd}")
        response = self.send_command(cmd)
        print(f"Response: {response}")
        # Check if the message was sent successfully
        if response and "+OK" in response:
            return response
        return None

    def receive_data(self):
        # Check for incoming data, looking for the +RCV pattern
        response = self.get_response()
        if response:
            for line in response:
                if line.startswith("+RCV"):
                    return line  # Return the received data in the format +RCV=Address,Length,Data,RSSI,SNR
        return None

    def get_uid(self):
        # Get the module's unique ID
        return self.send_command("AT+UID?")

    def get_version(self):
        # Get the module's firmware version
        return self.send_command("AT+VER?")

    def set_baud_rate(self, baudrate):
        # Set UART baud rate
        return self.send_command(f"AT+IPR={baudrate}")

    def close(self):
        # Close the serial connection
        if self.ser.is_open:
            self.ser.close()

# Example Usage
if __name__ == "__main__":
    lora = RYLR998(port='/dev/ttyAMA0')  # Replace with the appropriate port
    print(lora.reset())
    print(lora.set_address(120))
    print(lora.get_address())
    print(lora.set_network_id(6))
    print(lora.get_network_id())
    
    # Send and receive data
    print(lora.send_data(0, "HELLO"))
    while (x := lora.receive_data()) is None:
        print("Waiting for data...")
        time.sleep(1)
    print(x)

    print(lora.get_uid())
    print(lora.get_version())
    lora.close()
