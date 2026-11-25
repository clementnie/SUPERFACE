# Orange Pi UART2

The Orange Pi Zero 2W exposes UART2 on PI5 and PI6 through the 40-pin header. The terminal uses `/dev/ttyS2` at 3 Mbaud, 8N1, with no flow control. UART0 on PH0/PH1 remains an independent 115200-baud recovery console. See the wiring table in the [README](../README.md).

The verified Manjaro ARM 6.9.4 path enables `serial@5000800` and selects the PI5/PI6 pinmux. Its clock profile sets PLL_PERIPH0 to 576 MHz and APB2 to 48 MHz. UART2 uses divisor 1. The stock 24 MHz reference can only reach 1.5 Mbaud under the 8250 divisor model. APB2 is shared with UART0/1 and I²C. Keep the original boot entry and qualify its alternatives on the exact installed kernel and board.

## Prepare a recoverable boot entry

Use the scripts from `host/uart` with the board's original DTB and extlinux configuration. Apply the `uart2-pi.dts` overlay to a separate DTB, then use `build-clock-dtb.sh --stock PINMUX.dtb CLOCK.dtb`. Review the companion `render-extlinux.py` and `stage-extlinux.sh` for the boot-file layout. Preserve the installed boot configuration and select the new `superface-uart2-clock` entry once at the U-Boot prompt over UART0. Verify that UART0 and normal system access return before making a persistent boot change.

On Linux, `sh host/uart/find-tty.sh` checks the controller ancestry. With the tty idle and access granted, run `host/build/superface-uart --check /dev/ttyS2`. The verified clock profile reports `baud_base=3000000`, equivalent to a 48 MHz reference and divisor 1. Keep the UART clock assignments and pinmux together. A tty node alone does not establish that the link can operate at 3 Mbaud.

## Change the default after a successful trial

Read the current configuration and hash it. Then run `host/service/set-default-trial.py` with the current file, a new output path, and its SHA-256. Inspect the diff. The candidate changes a single default directive and keeps the fallback entries. Back up the original to a private directory on the root filesystem and record its SHA-256. Install the reviewed candidate to a temporary file on the same boot filesystem, sync, rename it over the original, and sync again.

Keep UART0 connected for the first reboot. Confirm that the original entry can still be selected and that the boot partition can be mounted from another machine. Restore the saved config using UART0 or the powered-off SD card if needed. If SSH depends on manually configured Wi-Fi, have the local UART0 procedure ready to bring up networking using existing profiles. SUPERFACE's systemd unit has no network dependency.
