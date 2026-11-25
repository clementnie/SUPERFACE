#!/usr/bin/env python3
"""Prepare a read-only Flash backup Quartus project in a fresh directory."""
import sys,shutil
from pathlib import Path
import phase5_schematics as b
source=Path(__file__).resolve().parents[1]; dest=Path(sys.argv[1]); dest.mkdir()
for p in source.iterdir():
 if p.suffix in ('.bdf','.bsf','.qsf','.qpf','.qip','.vhd','.mif','.sdc','.tdf','.inc'): shutil.copy2(p,dest/p.name)
b.HEADER='//#pragma file_not_in_maxplusii_format\n'+b.HEADER
b.ROOT=dest
b.generate()
b.PORTS['Display_Reset']=[('Clk','in',1),('KEY3_N','in',1),('Reset','out',1)]
ports=[('CLOCK_50','in',1),('CLOCK_24','in',2),('KEY','in',4),('UART_RX','in',1),('UART_TX','out',1),
       ('FL_DQ','in',8),('FL_ADDR','out',22),*[(f'FL_{v}_N','out',1) for v in ('CE','OE','WE','RST')],
       *[(f'SRAM_{v}_N','out',1) for v in ('CE','OE','WE')]]
b.sheet('Flash_Backup',ports,[
 ('Display_Reset','Reset_Release',560,96,dict(Clk='CLOCK_50',KEY3_N='KEY[3]',Reset='Board_Reset')),
 ('UART_PHY','Terminal_UART',560,350,dict(clk50='CLOCK_50',clk24='CLOCK_24[0]',board_reset='Board_Reset',
  serial_rx='UART_RX',serial_tx='UART_TX',rx_pop='Rx_Pop',rx_empty='Rx_Empty',rx_token='Rx_Token[8..0]',
  tx_push='Tx_Push',tx_full='Tx_Full',tx_token='Tx_Token[8..0]',frame_done='Frame_Done',
  reset50='Link_Reset',run50='Link_Run',framing_error='GND')),
 ('Parallel_Flash_Read','Read_Only_Array',1440,96,dict(clk='CLOCK_50',reset='Board_Reset',request='Flash_Request',
  address='Flash_Address[21..0]',flash_data='FL_DQ[7..0]',flash_addr='FL_ADDR[21..0]',
  **{f'{v}_n':f'FL_{v.upper()}_N' for v in ('ce','oe','we','rst')},ready='Flash_Ready',done='Flash_Done',data='Flash_Byte[7..0]')),
 ('Flash_Backup_Stream','Non_Destructive_Backup',1440,600,dict(clk='CLOCK_50',reset='Link_Reset',run='Link_Run',
  rx_pop='Rx_Pop',rx_empty='Rx_Empty',rx_token='Rx_Token[8..0]',tx_push='Tx_Push',tx_full='Tx_Full',tx_token='Tx_Token[8..0]',
  ground='GND',frame_done='Frame_Done',flash_ready='Flash_Ready',flash_done='Flash_Done',flash_request='Flash_Request',
  flash_data='Flash_Byte[7..0]',flash_address='Flash_Address[21..0]',**{f'sram_{v}_n':f'SRAM_{v.upper()}_N' for v in ('ce','oe','we')}))
],['Read-only 4MiB user Flash backup, UART trigger B, CRC32 trailer','Flash WE# is hard-wired high. SRAM strobes inactive. NO ERASE OR PROGRAM LOGIC.'])
(dest/'LAB8.bdf').write_text((dest/'Flash_Backup.bdf').read_text())
with (dest/'LAB8.qsf').open('a') as f:
 f.write('\nset_global_assignment -name VHDL_FILE Flash_Backup_Stream.vhd\nset_global_assignment -name RESERVE_ALL_UNUSED_PINS \"AS INPUT TRI-STATED\"\n')
# Duplicate package/loader files already in the Phase7 QSF; top entity remains LAB8.
(dest/'READ_ONLY_FLASH_BACKUP').touch()
