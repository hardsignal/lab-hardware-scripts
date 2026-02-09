import subprocess
import scipy.io.wavfile as wav

def power_on_device():
    cmd = "dp832 --set-voltage 5.0 --set-current-limit 1.0"
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 0:
        print("Device powered on successfully.")
    else:
        print(f"Failed to power on device: {result.stderr}")

def collect_data_from_oscilloscope():
    cmd = "sdsctl -c /dev/ttyUSB0 -p ch1,ch2 --save-waveform test_data.bin"
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 0:
        print("Data collected successfully.")
    else:
        print(f"Failed to collect data: {result.stderr}")

def analyze_waveform():
    sample_rate, data = wav.read('test_data.bin')
    
    print(f"Sample Rate: {sample_rate}, Data Size: {data.size}")

if __name__ == "__main__":
    power_on_device()
    collect_data_from_oscilloscope()
    analyze_waveform()
