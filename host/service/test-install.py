#!/usr/bin/env python3
"""Regression: absent sysusers.d and repeat install, without root/system changes.
Only the OS boundary commands are stubbed; the actual installer runs twice.
"""
import hashlib,os,shutil,subprocess,tempfile
from pathlib import Path
source=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='superface-installer-test.') as tmp:
 r=Path(tmp); host=r/'stage/host'; host.mkdir(parents=True)
 for name in ('service','login','uart'):shutil.copytree(source/name,host/name)
 (host/'build').mkdir()
 for name in ('superface','superface-uart'):(host/'build'/name).write_text('verified fixture executable\n')
 osroot=r/'os'; bindir=r/'commands'; bindir.mkdir()
 for name in ('var/backups','sys/devices/platform/soc/5000800.serial','usr/bin','opt/superface/bin','etc/systemd/system','etc/udev/rules.d'):(osroot/name).mkdir(parents=True,exist_ok=True)
 (osroot/'usr/bin/login').write_text('#!/bin/sh\n');(osroot/'usr/bin/login').chmod(0o755)
 script=(host/'service/install.sh').read_text()
 for prefix in ('/opt/','/etc/','/var/','/sys/','/usr/bin/login','/usr/local/bin','/usr/share/terminfo/'):
  script=script.replace(prefix,str(osroot)+prefix)
 (host/'service/install.sh').write_text(script)
 def command(name,body):
  p=bindir/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
 command('id','echo 0')
 command('fuser','exit 1')
 command('systemctl',f'''case "$1" in
 is-active) test -e '{r}/active';;
 is-enabled) test -e '{r}/active';;
 enable) touch '{r}/active';;
 status) exit 0;;
 *) exit 0;;
esac''')
 command('install','''args=''
# Strip only fixture ownership requests; real install handles directory/mode/copy.
exec python3 - "$@" <<'PY'
import os,sys
args=[];i=1
while i<len(sys.argv):
 if sys.argv[i] in ('-o','-g'):i+=2
 else:args.append(sys.argv[i]);i+=1
os.execv('/usr/bin/install',['install']+args)
PY''')
 for name in ('systemd-sysusers','udevadm','systemd-analyze'):command(name,'exit 0')
 files=[host/'build/superface',host/'build/superface-uart',*sorted((host/'service').glob('*')),host/'login/superface.conf',host/'uart/find-tty.sh']
 (host/'SERVICE-SHA256SUMS').write_text(''.join(f'{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(host)}\n' for f in files if f.is_file()))
 env={**os.environ,'PATH':str(bindir)+':'+os.environ['PATH']}
 for run in range(2):
  result=subprocess.run(['sh',str(host/'service/install.sh')],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  assert result.returncode==0,result.stdout
 assert (osroot/'etc/sysusers.d/superface.conf').is_file()
 assert (osroot/'etc/systemd/system/superface.service').is_file()
 assert (osroot/'usr/local/bin/superface-layout').is_file()
 assert len(list((osroot/'var/backups').iterdir()))==1,'Identical rerun should avoid a new backup/restart'
 assert 'Identical installation already running' in result.stdout
 layout_script = osroot/'usr/local/bin/superface-layout'
 layout_script.write_text(layout_script.read_text().replace('/etc/', str(osroot) + '/etc/'))
 layout_override = osroot/'etc/systemd/system/superface.service.d/50-keyboard.conf'
 restarts = r/'restarts'
 command('systemctl', fr'''case "$1" in
 show)
   app='{layout_override}'
   if [ ! -f "$app" ]; then app='{osroot}/etc/systemd/system/superface.service'; fi
   sed -n 's/^ExecStart=\(.* --keyboard .*\)$/\1 ;/p' "$app";;
 daemon-reload) exit 0;;
 restart) [ "$2" = superface.service ] && echo restart >> '{restarts}';;
 *) exit 2;;
esac''')
 for layout in ('colemak', 'qwerty', 'colemak'):
  run = subprocess.run([str(layout_script), layout], env=env, check=True, text=True, capture_output=True)
  assert run.stdout.splitlines()[-1] == layout, run.stdout
  status = subprocess.check_output([str(layout_script), 'status'], env=env, text=True)
  assert status.strip() == layout
 assert restarts.read_text().splitlines() == ['restart'] * 3
 command('id', 'echo 1000')
 assert subprocess.run([str(layout_script), 'qwerty'], env=env, capture_output=True).returncode == 1
 assert subprocess.check_output([str(layout_script), 'status'], env=env, text=True).strip() == 'colemak'
 print('PASS actual installer: creates missing directories and skips identical active reinstall')
 print('PASS layout command: both selections persist, restart the service, and report status without root')
