import csv
from datetime import datetime
from getpass import getpass
from pathlib import Path

import paramiko


DEVICE_FILE = Path("config/devices.csv")
OUTPUT_DIR = Path("output")

COMMANDS = {
    "windows": [
        "hostname",
        "whoami",
        "ipconfig",
    ],
}


def decode_output(data: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


def load_devices():
    devices = []

    with DEVICE_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            row["port"] = int(row["port"])
            devices.append(row)

    return devices


def inspect_device(device, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    results = []

    try:
        print(
            f"\n[连接] {device['name']} "
            f"{device['host']}:{device['port']}"
        )

        client.connect(
            hostname=device["host"],
            port=device["port"],
            username=device["username"],
            password=password,
            timeout=10,
            auth_timeout=10,
            banner_timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )

        print(f"[成功] {device['name']} SSH连接成功")

        commands = COMMANDS.get(device["device_type"], [])

        for command in commands:
            print(f"  [执行] {command}")

            stdin, stdout, stderr = client.exec_command(command)

            output = decode_output(stdout.read()).strip()
            error = decode_output(stderr.read()).strip()

            section = [
                "=" * 60,
                f"DEVICE: {device['name']}",
                f"COMMAND: {command}",
                "=" * 60,
                output,
            ]

            if error:
                section.extend([
                    "",
                    "[STDERR]",
                    error,
                ])

            results.append("\n".join(section))

        return True, "\n\n".join(results)

    except paramiko.AuthenticationException:
        return False, "SSH认证失败"

    except paramiko.SSHException as error:
        return False, f"SSH协议错误：{error}"

    except Exception as error:
        return False, f"连接失败：{error}"

    finally:
        client.close()


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    devices = load_devices()

    if not devices:
        print("设备清单为空。")
        return

    print(f"读取到 {len(devices)} 台设备")

    password = getpass("SSH password: ")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    success_count = 0
    failed_count = 0

    for device in devices:
        success, result = inspect_device(device, password)

        if success:
            success_count += 1

            output_file = (
                OUTPUT_DIR
                / f"{device['name']}_{timestamp}.txt"
            )

            output_file.write_text(
                result,
                encoding="utf-8",
            )

            print(f"[保存] {output_file}")

        else:
            failed_count += 1
            print(f"[失败] {device['name']}：{result}")

    print("\n========== 巡检汇总 ==========")
    print(f"设备总数：{len(devices)}")
    print(f"成功：{success_count}")
    print(f"失败：{failed_count}")


if __name__ == "__main__":
    main()