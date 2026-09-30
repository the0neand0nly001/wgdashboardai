"""Explicit host helper for extending only the existing dashboard SSH link."""
import argparse
from pathlib import Path
import shutil
import subprocess
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=['vpn1', 'vpn2'])
    args = parser.parse_args()
    stamp = time.strftime('%Y%m%d-%H%M%S')
    if args.role == 'vpn1':
        path = Path('/home/ubuntu/.ssh/authorized_keys')
        text = path.read_text()
        lines = text.splitlines()
        matches = [i for i, line in enumerate(lines) if line.endswith('eh-vpn-dashboard-link')]
        if len(matches) != 1:
            raise SystemExit('Expected one existing restricted dashboard key; inspect manually')
        line = lines[matches[0]]
        if 'permitopen="127.0.0.1:8791"' not in line:
            if 'permitopen="127.0.0.1:8790"' not in line:
                raise SystemExit('Unexpected SSH restrictions; leaving the key unchanged')
            lines[matches[0]] = line.replace('permitopen="127.0.0.1:8790"', 'permitopen="127.0.0.1:8790",permitopen="127.0.0.1:8791"')
            shutil.copy2(path, str(path) + '.eh-backup-' + stamp)
            path.write_text('\n'.join(lines) + '\n')
    else:
        path = Path('/etc/systemd/system/eh-vpn-link.service')
        text = path.read_text()
        if '-L 127.0.0.1:18791:127.0.0.1:8791' not in text:
            marker = '-L 127.0.0.1:18790:127.0.0.1:8790'
            if marker not in text:
                raise SystemExit('Unexpected existing SSH service; leaving it unchanged')
            shutil.copy2(path, str(path) + '.eh-backup-' + stamp)
            path.write_text(text.replace(marker, marker + ' -L 127.0.0.1:18791:127.0.0.1:8791'))
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'restart', 'eh-vpn-link'], check=True)
    print('Existing restricted private link extended; unrelated SSH keys are unchanged.')

if __name__ == '__main__':
    main()
