import serial
import time

class RYLR998:
    def __init__(self, port, baudrate=115200, timeout=1):
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        time.sleep(2)  # Allow time for the module to initialize

    def send_command(self, command):
        full_command = f"{command}\r\n"
        self.ser.write(full_command.encode())
        time.sleep(0.1)
        return self.get_response()

    def get_response(self):
        response = []
        start_time = time.time()
        while time.time() - start_time < 1:  # Wait for up to 1 second
            if self.ser.in_waiting > 0:
                line = self.ser.readline().decode('utf-8').strip()
                if line:
                    response.append(line)
            else:
                time.sleep(0.1)
        return response if response else None

    def reset(self):
        return self.send_command("AT+RESET")

    def set_address(self, address):
        return self.send_command(f"AT+ADDRESS={address}")

    def get_address(self):
        return self.send_command("AT+ADDRESS?")

    def set_network_id(self, network_id):
        return self.send_command(f"AT+NETWORKID={network_id}")

    def get_network_id(self):
        return self.send_command("AT+NETWORKID?")
    
    def get_band(self):
        return self.send_command(f"AT+BAND?")
    
    def set_band(self, band):
        return self.send_command(f"AT+BAND={band}")

    def set_rf_parameters(self, spreading_factor, bandwidth, coding_rate, preamble):
        return self.send_command(f"AT+PARAMETER={spreading_factor},{bandwidth},{coding_rate},{preamble}")

    def send_data(self, address, data):
        length = len(data)
        response = self.send_command(f"AT+SEND={address},{length},{data}")
        print(f"Sent Data: {data}({length})\nResponse:{response}")
        if response and "+OK" in response:
            return response
        return None

    def receive_data(self):
        received_data = []
        start_time = time.time()
        if self.ser.in_waiting > 0:
            line = self.ser.readline().decode('utf-8').strip()
            if line:
                if line.startswith("+RCV="):
                    print(line)
                    # Parse the received data
                    parts = line[5:].strip().split(',')
                    print(parts)
                    if len(parts) >= 5:
                        received_data.append({
                            'address': int(parts[0]),
                            'length': int(parts[1]),
                            'data': parts[2],
                            'rssi': int(parts[3]),
                            'snr': float(parts[4])
                        })
        
        return received_data if received_data else None

    def get_uid(self):
        return self.send_command("AT+UID?")

    def get_version(self):
        return self.send_command("AT+VER?")

    def set_baud_rate(self, baudrate):
        return self.send_command(f"AT+IPR={baudrate}")

    def close(self):
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
    
    print(lora.send_data(0, "HELLO"))
    
    print("Waiting for data...")
    for _ in range(10):  # Try to receive data for 10 seconds
        received = lora.receive_data()
        if received:
            for item in received:
                if 'data' in item:
                    print(f"Received: Address={item['address']}, Length={item['length']}, "
                          f"Data={item['data']}, RSSI={item['rssi']}, SNR={item['snr']}")
                else:
                    print(f"Other response: {item['other']}")
        time.sleep(1)

    print(lora.get_uid())
    print(lora.get_version())
    lora.close()