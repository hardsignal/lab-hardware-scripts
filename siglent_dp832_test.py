import pyvisa

rm = pyvisa.ResourceManager()

# Rigol DP832 via USB
dp = rm.open_resource('USB0::0x1AB1::0x0E11::DP8C272902771::INSTR')
print("DP832 ID:", dp.query('*IDN?').strip())

# Siglent SDL load
sdl = rm.open_resource('TCPIP::192.168.1.194::inst0::INSTR')
print("SDL ID:", sdl.query('*IDN?').strip())

# Siglent SDS scope
sds = rm.open_resource('TCPIP::192.168.1.170::inst0::INSTR')
print("SDS ID:", sds.query('*IDN?').strip())

dp.close()
sdl.close()
sds.close()
rm.close()
