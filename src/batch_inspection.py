import csv
import logging
from datetime import datetime
from getpass import getpass
from pathlib import Path

import paramiko


DEVICE_FILE = Path("config/devices.csv")
OUTPUT_DIR = Path("output")
LOG_DIR = Path("logs")

COMMANDS = {
    "windows": [
        "hostname",
        "whoami",
        "ipconfig",
    ],
}


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)

    log_file = LOG_DIR / "inspection.log"

    logger = logging.getLogger("inspection")
    logger.setLevel(logging.INFO)

    # 防止重复添加 Handler
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(
        log_file,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


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
        logger.info(
            "开始连接设备 %s (%s:%s)",
            device["name"],
            device["host"],
            device["port"],
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

        logger.info(
            "设备 %s SSH连接成功",
            device["name"],
        )

        commands = COMMANDS.get(device["device_type"])

        if commands is None:
            return False, (
                f"未知设备类型：{device['device_type']}"
            )

        for command in commands:
            logger.info(
                "设备 %s 执行命令：%s",
                device["name"],
                command,
            )

            stdin, stdout, stderr = client.exec_command(
                command
            )

            output = decode_output(
                stdout.read()
            ).strip()

            error = decode_output(
                stderr.read()
            ).strip()

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

                logger.warning(
                    "设备 %s 命令 %s 返回错误信息",
                    device["name"],
                    command,
                )

            results.append(
                "\n".join(section)
            )

        return True, "\n\n".join(results)

    except paramiko.AuthenticationException:
        logger.error(
            "设备 %s SSH认证失败",
            device["name"],
        )
        return False, "SSH认证失败"

    except paramiko.SSHException as error:
        logger.error(
            "设备 %s SSH协议错误：%s",
            device["name"],
            error,
        )
        return False, f"SSH协议错误：{error}"

    except Exception as error:
        logger.error(
            "设备 %s 连接失败：%s",
            device["name"],
            error,
        )
        return False, f"连接失败：{error}"

    finally:
        client.close()


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    devices = load_devices()

    if not devices:
        logger.warning("设备清单为空")
        return

    logger.info(
        "本次巡检读取到 %s 台设备",
        len(devices),
    )

    password = getpass("SSH password: ")

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    success_count = 0
    failed_count = 0

    for device in devices:

        success, result = inspect_device(
            device,
            password,
        )

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

            logger.info(
                "设备 %s 巡检结果保存至 %s",
                device["name"],
                output_file,
            )

        else:
            failed_count += 1

            logger.error(
                "设备 %s 巡检失败：%s",
                device["name"],
                result,
            )

    logger.info(
        "巡检结束 | 总数=%s | 成功=%s | 失败=%s",
        len(devices),
        success_count,
        failed_count,
    )


if __name__ == "__main__":
    main()