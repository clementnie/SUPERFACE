# Install the authenticated terminal

On the Orange Pi, build the pinned libvterm fork and run `make -C host check`. Confirm that the 48 MHz UART2 entry is running, the matching FPGA image is configured, and other applications have released `/dev/ttyS2`.

From the `host` directory, stage and checksum the files installed by the service.

```sh
sha256sum build/superface build/superface-uart \
  service/install.sh service/check-uart service/superface.service \
  service/70-superface-uart.rules service/superface.terminfo \
  login/superface.conf uart/find-tty.sh > SERVICE-SHA256SUMS
sudo sh service/install.sh
```

The installer needs `tic`, systemd, udev and PAM's `/usr/bin/login`. Systemd starts the launcher as root to fork `login(1)`. The UART and terminal renderer run as the dedicated `superface` account after permanently dropping privileges. The rule identifies UART2 by controller ancestry and restricts access to root and the service group. Remove any temporary development ACL after testing. Normal SIGTERM shutdown is successful. Other nonzero exits retain their normal failure behavior.

### Keyboard layout

The production service uses standard Colemak for the physical login prompt and shell. Physical Caps Lock sends Backspace and repeats when held. The physical Backspace key works in both layouts. QWERTY uses conventional Caps Lock.

Switch to QWERTY with a persistent systemd override.

```sh
sudo install -d /etc/systemd/system/superface.service.d
sudo tee /etc/systemd/system/superface.service.d/50-keyboard.conf >/dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=/opt/superface/bin/superface --login --keyboard qwerty --uart /dev/ttyS2
EOF
sudo systemctl daemon-reload
```

Switch to Colemak by restoring the stock service command.

```sh
sudo rm -f /etc/systemd/system/superface.service.d/50-keyboard.conf
sudo systemctl daemon-reload
```

Check the configured layout.

```sh
systemctl show -p ExecStart --value superface.service |
  sed -n 's/.*--keyboard \(colemak\|qwerty\).*/\1/p'
```

Apply the configured layout to both the physical login prompt and shell. **Restarting the service terminates the current physical login session.** Run this command over SSH or the UART0 console if available.

```sh
sudo systemctl restart superface.service
```

Confirm a private physical PAM login and run `stty size`. It should print `30 80`. The installer prints the rollback directory. To revert, stop the service, restore the backed-up files to their original paths and remove only the new files absent from that backup, including the terminfo entry if applicable. Reload systemd and the udev rules. Restore the previous enablement state recorded in the backup.

## Standalone boot

On the Orange Pi, make the tested 48 MHz UART2 entry the extlinux default using the [UART2 recovery procedure](../../docs/SUPERFACE_UART2.md). The service starts from `multi-user.target` and does not need a network connection.

On the DE1, convert the release SOF to an EPCS4 programming file with `quartus_cpf --64bit -c -d EPCS4 LAB8.sof LAB8-EPCS4.pof`. In Active Serial mode, put the RUN/PROG switch in PROG and identify the EPCS4 before writing it. Save its original contents and verify the saved POF against the device.

```sh
quartus_pgm --64bit -c CABLE -m AS -o 'e;original-epcs4.pof;EPCS4'
quartus_pgm --64bit -c CABLE -m AS -o 'v;original-epcs4.pof'
sha256sum original-epcs4.pof
quartus_pgm --64bit -c CABLE -m AS -o 'pv;LAB8-EPCS4.pof'
```

Keep the original POF private. To roll back, use its recorded hash and Program + Verify with the same cable, mode, and switch position. Return the switch to RUN and power-cycle the board after programming. EPCS4 stores the FPGA image independently of the U9 font Flash. [Terasic DE1 User Manual](https://www.terasic.com.tw/attachment/archive/83/DE1_UserManual_v1018.pdf)
