import re
from pathlib import Path


# ============================================================
# 项目目录
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_DIR = BASE_DIR / "output"


# ============================================================
# 当前实验设备的期望状态
# ============================================================

DEVICE_NAME = "AR1"

EXPECTED_INTERFACE = "Ethernet0/0/8"

EXPECTED_IP = "192.168.100.2/24"

EXPECTED_ROUTE = "192.168.100.0/24"


# ============================================================
# 找到最近一次巡检结果
# ============================================================

def get_latest_inspection_file():

    files = list(
        OUTPUT_DIR.glob(
            f"{DEVICE_NAME}_console_*.txt"
        )
    )

    if not files:
        raise FileNotFoundError(
            "没有找到 Huawei 巡检结果文件，"
            "请先运行 huawei_console_test.py。"
        )

    latest_file = max(
        files,
        key=lambda file: file.stat().st_mtime,
    )

    return latest_file


# ============================================================
# 接口状态分析
# ============================================================

def check_interface(text):

    """
    检查目标接口：

        Ethernet0/0/8

    重点判断：

        IP地址
        Physical
        Protocol
    """

    for raw_line in text.splitlines():

        line = raw_line.strip()

        if not line.startswith(
            EXPECTED_INTERFACE
        ):
            continue

        # Huawei 输出通常类似：
        #
        # Ethernet0/0/8
        # 192.168.100.2/24
        # up
        # up
        #
        # 实际是一行多个字段

        fields = line.split()

        if len(fields) < 4:

            return {
                "status": "WARNING",
                "interface": EXPECTED_INTERFACE,
                "ip": "UNKNOWN",
                "physical": "UNKNOWN",
                "protocol": "UNKNOWN",
                "detail": "接口信息字段不完整",
            }

        interface = fields[0]
        ip_address = fields[1]
        physical = fields[2]
        protocol = fields[3]

        problems = []

        # ----------------------------------------------------
        # IP地址判断
        # ----------------------------------------------------

        if ip_address != EXPECTED_IP:

            problems.append(
                f"IP异常：当前={ip_address}，"
                f"期望={EXPECTED_IP}"
            )

        # ----------------------------------------------------
        # Physical状态判断
        # ----------------------------------------------------

        if physical.lower() != "up":

            problems.append(
                f"Physical={physical}"
            )

        # ----------------------------------------------------
        # Protocol状态判断
        # ----------------------------------------------------

        if not protocol.lower().startswith(
            "up"
        ):

            problems.append(
                f"Protocol={protocol}"
            )

        # ----------------------------------------------------
        # 生成最终状态
        # ----------------------------------------------------

        if problems:

            return {
                "status": "WARNING",
                "interface": interface,
                "ip": ip_address,
                "physical": physical,
                "protocol": protocol,
                "detail": "；".join(problems),
            }

        return {
            "status": "NORMAL",
            "interface": interface,
            "ip": ip_address,
            "physical": physical,
            "protocol": protocol,
            "detail": (
                "接口IP正确，"
                "Physical/Protocol均为up"
            ),
        }

    # 根本没有找到目标接口

    return {
        "status": "WARNING",
        "interface": EXPECTED_INTERFACE,
        "ip": "UNKNOWN",
        "physical": "UNKNOWN",
        "protocol": "UNKNOWN",
        "detail": "未找到目标接口",
    }


# ============================================================
# 路由状态分析
# ============================================================

def check_route(text):

    """
    检查路由表中是否存在：

        192.168.100.0/24

    正常情况下：

        Ethernet0/0/8
        192.168.100.2/24

    会自动生成：

        192.168.100.0/24 Direct
    """

    for raw_line in text.splitlines():

        line = raw_line.strip()

        if EXPECTED_ROUTE not in line:
            continue

        fields = line.split()

        # 找到了目标网段

        route_type = "UNKNOWN"

        for field in fields:

            if field.lower() in {
                "direct",
                "static",
                "ospf",
                "rip",
                "isis",
                "bgp",
            }:

                route_type = field

                break

        return {
            "status": "NORMAL",
            "route": EXPECTED_ROUTE,
            "route_type": route_type,
            "detail": (
                f"目标路由存在，"
                f"路由类型={route_type}"
            ),
        }

    # 没找到目标网段

    return {
        "status": "WARNING",
        "route": EXPECTED_ROUTE,
        "route_type": "UNKNOWN",
        "detail": "目标路由不存在",
    }


# ============================================================
# 计算总体状态
# ============================================================

def calculate_overall_status(
    interface_result,
    route_result,
):

    if (
        interface_result["status"]
        == "WARNING"
    ):

        return "WARNING"

    if (
        route_result["status"]
        == "WARNING"
    ):

        return "WARNING"

    return "NORMAL"


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        "=" * 60
    )

    print(
        "Huawei 网络状态自动分析"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # 获取最新巡检文件
    # --------------------------------------------------------

    latest_file = (
        get_latest_inspection_file()
    )

    print(
        f"分析文件：{latest_file.name}"
    )

    print()

    text = latest_file.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    # ========================================================
    # 接口检查
    # ========================================================

    interface_result = (
        check_interface(text)
    )

    print(
        "[接口状态检查]"
    )

    print(
        f"接口："
        f"{interface_result['interface']}"
    )

    print(
        f"IP："
        f"{interface_result['ip']}"
    )

    print(
        f"Physical："
        f"{interface_result['physical']}"
    )

    print(
        f"Protocol："
        f"{interface_result['protocol']}"
    )

    print(
        f"状态："
        f"{interface_result['status']}"
    )

    print(
        f"说明："
        f"{interface_result['detail']}"
    )

    print()

    # ========================================================
    # 路由检查
    # ========================================================

    route_result = (
        check_route(text)
    )

    print(
        "[路由状态检查]"
    )

    print(
        f"目标网段："
        f"{route_result['route']}"
    )

    print(
        f"路由类型："
        f"{route_result['route_type']}"
    )

    print(
        f"状态："
        f"{route_result['status']}"
    )

    print(
        f"说明："
        f"{route_result['detail']}"
    )

    print()

    # ========================================================
    # 总体判断
    # ========================================================

    overall_status = (
        calculate_overall_status(
            interface_result,
            route_result,
        )
    )

    print(
        "=" * 60
    )

    print(
        f"{DEVICE_NAME} 总体状态："
        f"{overall_status}"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()