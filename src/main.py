import csv
import logging
from datetime import datetime
from getpass import getpass
from pathlib import Path

import paramiko


# =========================
# 项目目录
# =========================

DEVICE_FILE = Path("config/devices.csv")

OUTPUT_DIR = Path("output")
BACKUP_DIR = Path("backup")
LOG_DIR = Path("logs")
REPORT_DIR = Path("reports")


# =========================
# 不同设备类型的巡检命令
# =========================

COMMANDS = {
    "windows": [
        "hostname",
        "whoami",
        "ipconfig",
    ],
}


# =========================
# 不同设备类型的配置备份命令
# =========================

BACKUP_COMMANDS = {
    "windows": "ipconfig /all",
}


# =========================
# 日志系统
# =========================

def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("network_inspection")
    logger.setLevel(logging.INFO)

    # 防止重复添加 Handler
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(
        LOG_DIR / "inspection.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


# =========================
# 编码处理
# =========================

def decode_output(data: bytes) -> str:
    """
    尝试使用 UTF-8 和 GBK 解码远程命令输出。
    """

    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode(
        "utf-8",
        errors="replace",
    )


# =========================
# 读取设备清单
# =========================

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


# =========================
# SSH连接
# =========================

def connect_device(device, password):
    client = paramiko.SSHClient()

    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
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

    return client


# =========================
# 执行单条命令
# =========================

def run_command(client, command):
    stdin, stdout, stderr = client.exec_command(
        command
    )

    output = decode_output(
        stdout.read()
    ).strip()

    error = decode_output(
        stderr.read()
    ).strip()

    return output, error


# =========================
# 执行设备巡检
# =========================

def run_inspection(client, device, timestamp):
    device_type = device["device_type"]

    commands = COMMANDS.get(
        device_type
    )

    if commands is None:
        raise ValueError(
            f"不支持的设备类型：{device_type}"
        )

    results = []

    for command in commands:

        logger.info(
            "设备 %s 执行巡检命令：%s",
            device["name"],
            command,
        )

        output, error = run_command(
            client,
            command,
        )

        section = [
            "=" * 60,
            f"DEVICE: {device['name']}",
            f"HOST: {device['host']}",
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
                "设备 %s 命令 %s 存在错误输出",
                device["name"],
                command,
            )

        results.append(
            "\n".join(section)
        )

    OUTPUT_DIR.mkdir(
        exist_ok=True
    )

    output_file = (
        OUTPUT_DIR
        / f"{device['name']}_{timestamp}.txt"
    )

    output_file.write_text(
        "\n\n".join(results),
        encoding="utf-8",
    )

    logger.info(
        "设备 %s 巡检结果保存至 %s",
        device["name"],
        output_file,
    )


# =========================
# 配置备份
# =========================

def backup_configuration(
    client,
    device,
    timestamp,
):
    device_type = device["device_type"]

    command = BACKUP_COMMANDS.get(
        device_type
    )

    if command is None:
        logger.warning(
            "设备 %s 暂无配置备份命令",
            device["name"],
        )
        return

    logger.info(
        "设备 %s 执行配置备份命令：%s",
        device["name"],
        command,
    )

    output, error = run_command(
        client,
        command,
    )

    if error:
        logger.warning(
            "设备 %s 备份命令存在错误输出：%s",
            device["name"],
            error,
        )

    device_backup_dir = (
        BACKUP_DIR / device["name"]
    )

    device_backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup_file = (
        device_backup_dir
        / f"{device['name']}_{timestamp}.txt"
    )

    backup_file.write_text(
        output,
        encoding="utf-8",
    )

    logger.info(
        "设备 %s 配置备份保存至 %s",
        device["name"],
        backup_file,
    )


# =========================
# 巡检单台设备
# =========================

def inspect_device(
    device,
    password,
    timestamp,
):
    client = None

    try:
        logger.info(
            "开始连接设备 %s (%s:%s)",
            device["name"],
            device["host"],
            device["port"],
        )

        client = connect_device(
            device,
            password,
        )

        logger.info(
            "设备 %s SSH连接成功",
            device["name"],
        )

        run_inspection(
            client,
            device,
            timestamp,
        )

        backup_configuration(
            client,
            device,
            timestamp,
        )

        return True, "巡检成功"

    except paramiko.AuthenticationException:
        message = "SSH认证失败"

        logger.error(
            "设备 %s %s",
            device["name"],
            message,
        )

        return False, message

    except paramiko.SSHException as error:
        message = (
            f"SSH协议错误：{error}"
        )

        logger.error(
            "设备 %s %s",
            device["name"],
            message,
        )

        return False, message

    except Exception as error:
        message = (
            f"巡检失败：{error}"
        )

        logger.error(
            "设备 %s %s",
            device["name"],
            message,
        )

        return False, message

    finally:
        if client is not None:
            client.close()


# =========================
# 生成CSV汇总报告
# =========================

def generate_csv_report(
    summary_rows,
    timestamp,
):
    REPORT_DIR.mkdir(
        exist_ok=True
    )

    report_file = (
        REPORT_DIR
        / f"inspection_summary_{timestamp}.csv"
    )

    fieldnames = [
        "time",
        "name",
        "host",
        "port",
        "device_type",
        "status",
        "message",
    ]

    with report_file.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            summary_rows
        )

    logger.info(
        "巡检汇总报告保存至 %s",
        report_file,
    )

    return report_file


# =========================
# 主程序
# =========================

def main():
    devices = load_devices()

    if not devices:
        logger.warning(
            "设备清单为空"
        )
        return

    logger.info(
        "========== 开始网络设备巡检 =========="
    )

    logger.info(
        "本次读取到 %s 台设备",
        len(devices),
    )

    password = getpass(
        "SSH password: "
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    success_count = 0
    failed_count = 0

    summary_rows = []

    for device in devices:

        success, message = inspect_device(
            device,
            password,
            timestamp,
        )

        if success:
            success_count += 1
        else:
            failed_count += 1

        summary_rows.append({
            "time": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "name": device["name"],
            "host": device["host"],
            "port": device["port"],
            "device_type": device["device_type"],
            "status": (
                "SUCCESS"
                if success
                else "FAILED"
            ),
            "message": message,
        })

    generate_csv_report(
        summary_rows,
        timestamp,
    )

    logger.info(
        "巡检结束 | 总数=%s | 成功=%s | 失败=%s",
        len(devices),
        success_count,
        failed_count,
    )

    logger.info(
        "========== 本次巡检完成 =========="
    )


if __name__ == "__main__":
    main()