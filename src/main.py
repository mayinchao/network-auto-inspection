import csv
import logging
from datetime import datetime
from getpass import getpass
from pathlib import Path

import paramiko

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ============================================================
# 项目路径
# ============================================================

DEVICE_FILE = Path("config/devices.csv")

OUTPUT_DIR = Path("output")
BACKUP_DIR = Path("backup")
LOG_DIR = Path("logs")
REPORT_DIR = Path("reports")


# ============================================================
# 不同设备类型的巡检命令
# ============================================================

COMMANDS = {
    "windows": [
        "hostname",
        "whoami",
        "ipconfig",
    ],
}


# ============================================================
# 不同设备类型的配置备份命令
# ============================================================

BACKUP_COMMANDS = {
    "windows": "ipconfig /all",
}


# ============================================================
# 日志系统
# ============================================================

def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("network_inspection")
    logger.setLevel(logging.INFO)

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


# ============================================================
# 命令输出编码处理
# ============================================================

def decode_output(data: bytes) -> str:
    """
    尝试处理 Windows 中文输出。
    后续接入华为设备时也可以继续扩展。
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


# ============================================================
# 加载设备清单
# ============================================================

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


# ============================================================
# SSH连接
# ============================================================

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


# ============================================================
# 执行单条命令
# ============================================================

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


# ============================================================
# 执行巡检命令
# ============================================================

def run_inspection(
    client,
    device,
    timestamp,
):
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

    return output_file


# ============================================================
# 配置备份
# ============================================================

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
        return None

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

    return backup_file


# ============================================================
# 巡检单台设备
# ============================================================

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


# ============================================================
# CSV汇总报告
# ============================================================

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
        "CSV巡检报告保存至 %s",
        report_file,
    )

    return report_file


# ============================================================
# Excel汇总报告
# ============================================================

def generate_excel_report(
    summary_rows,
    timestamp,
    success_count,
    failed_count,
):
    REPORT_DIR.mkdir(
        exist_ok=True
    )

    report_file = (
        REPORT_DIR
        / f"inspection_summary_{timestamp}.xlsx"
    )

    workbook = Workbook()

    # --------------------------------------------------------
    # 巡检汇总 Sheet
    # --------------------------------------------------------

    sheet = workbook.active
    sheet.title = "巡检汇总"

    sheet.merge_cells(
        "A1:G1"
    )

    title_cell = sheet["A1"]
    title_cell.value = "网络设备自动巡检汇总报告"
    title_cell.font = Font(
        bold=True,
        size=16,
    )
    title_cell.alignment = Alignment(
        horizontal="center",
        vertical="center",
    )

    sheet.row_dimensions[1].height = 28

    sheet["A2"] = "生成时间"
    sheet["B2"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    headers = [
        "巡检时间",
        "设备名称",
        "管理地址",
        "SSH端口",
        "设备类型",
        "状态",
        "说明",
    ]

    header_row = 4

    for column_index, header in enumerate(
        headers,
        start=1,
    ):
        cell = sheet.cell(
            row=header_row,
            column=column_index,
        )

        cell.value = header

        cell.font = Font(
            bold=True
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        cell.fill = PatternFill(
            fill_type="solid",
            fgColor="D9EAF7",
        )

    for row_index, row_data in enumerate(
        summary_rows,
        start=5,
    ):
        values = [
            row_data["time"],
            row_data["name"],
            row_data["host"],
            row_data["port"],
            row_data["device_type"],
            row_data["status"],
            row_data["message"],
        ]

        for column_index, value in enumerate(
            values,
            start=1,
        ):
            cell = sheet.cell(
                row=row_index,
                column=column_index,
            )

            cell.value = value

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

        status_cell = sheet.cell(
            row=row_index,
            column=6,
        )

        status_cell.font = Font(
            bold=True
        )

        status_cell.alignment = Alignment(
            horizontal="center",
        )

        if row_data["status"] == "SUCCESS":
            status_cell.fill = PatternFill(
                fill_type="solid",
                fgColor="C6EFCE",
            )
        else:
            status_cell.fill = PatternFill(
                fill_type="solid",
                fgColor="FFC7CE",
            )

    sheet.freeze_panes = "A5"

    if summary_rows:
        sheet.auto_filter.ref = (
            f"A4:G{sheet.max_row}"
        )

    column_widths = {
        "A": 21,
        "B": 18,
        "C": 18,
        "D": 12,
        "E": 16,
        "F": 12,
        "G": 55,
    }

    for column, width in column_widths.items():
        sheet.column_dimensions[
            column
        ].width = width

    # --------------------------------------------------------
    # 统计 Sheet
    # --------------------------------------------------------

    stats_sheet = workbook.create_sheet(
        "统计"
    )

    stats_sheet.merge_cells(
        "A1:B1"
    )

    stats_sheet["A1"] = "巡检统计"

    stats_sheet["A1"].font = Font(
        bold=True,
        size=15,
    )

    stats_sheet["A1"].alignment = Alignment(
        horizontal="center",
    )

    total_count = len(
        summary_rows
    )

    if total_count:
        success_rate = (
            success_count / total_count
        )
    else:
        success_rate = 0

    stats_data = [
        ("设备总数", total_count),
        ("巡检成功", success_count),
        ("巡检失败", failed_count),
        ("成功率", success_rate),
    ]

    for row_index, (
        label,
        value,
    ) in enumerate(
        stats_data,
        start=3,
    ):
        stats_sheet.cell(
            row=row_index,
            column=1,
            value=label,
        )

        stats_sheet.cell(
            row=row_index,
            column=2,
            value=value,
        )

        stats_sheet.cell(
            row=row_index,
            column=1,
        ).font = Font(
            bold=True
        )

    stats_sheet["B6"].number_format = "0.00%"

    stats_sheet.column_dimensions[
        "A"
    ].width = 18

    stats_sheet.column_dimensions[
        "B"
    ].width = 18

    # --------------------------------------------------------
    # 异常设备 Sheet
    # --------------------------------------------------------

    failed_devices = [
        row
        for row in summary_rows
        if row["status"] == "FAILED"
    ]

    error_sheet = workbook.create_sheet(
        "异常设备"
    )

    error_headers = [
        "时间",
        "设备名称",
        "地址",
        "端口",
        "设备类型",
        "失败原因",
    ]

    for column_index, header in enumerate(
        error_headers,
        start=1,
    ):
        cell = error_sheet.cell(
            row=1,
            column=column_index,
            value=header,
        )

        cell.font = Font(
            bold=True
        )

        cell.fill = PatternFill(
            fill_type="solid",
            fgColor="F4CCCC",
        )

        cell.alignment = Alignment(
            horizontal="center",
        )

    for row_index, row_data in enumerate(
        failed_devices,
        start=2,
    ):
        values = [
            row_data["time"],
            row_data["name"],
            row_data["host"],
            row_data["port"],
            row_data["device_type"],
            row_data["message"],
        ]

        for column_index, value in enumerate(
            values,
            start=1,
        ):
            cell = error_sheet.cell(
                row=row_index,
                column=column_index,
                value=value,
            )

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    error_widths = {
        "A": 21,
        "B": 18,
        "C": 18,
        "D": 12,
        "E": 16,
        "F": 60,
    }

    for column, width in error_widths.items():
        error_sheet.column_dimensions[
            column
        ].width = width

    error_sheet.freeze_panes = "A2"

    # --------------------------------------------------------
    # 保存Excel
    # --------------------------------------------------------

    workbook.save(
        report_file
    )

    logger.info(
        "Excel巡检报告保存至 %s",
        report_file,
    )

    return report_file


# ============================================================
# 主程序
# ============================================================

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

    generate_excel_report(
        summary_rows,
        timestamp,
        success_count,
        failed_count,
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