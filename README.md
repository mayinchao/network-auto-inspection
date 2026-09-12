# 网络设备自动巡检与配置备份系统

基于 Python 开发的网络自动化巡检项目，用于批量连接 Windows 主机及 Huawei VRP 网络设备，自动执行巡检命令、备份配置、分析接口与路由状态，并生成 CSV / Excel 巡检报告。

项目目前已完成 Windows SSH 巡检和 eNSP Huawei 路由器 Console TCP 自动巡检，并通过接口故障注入实验验证异常检测能力。

---

## 1. 项目功能

### Windows 主机巡检

通过 Paramiko SSH 连接 Windows OpenSSH Server，自动执行：

- `hostname`
- `whoami`
- `ipconfig`

并使用：

- `ipconfig /all`

完成主机网络配置备份。

### Huawei VRP 自动巡检

通过 eNSP Console TCP 与 Huawei AR 路由器建立连接，自动执行：

- `display version`
- `display ip interface brief`
- `display ip routing-table`
- `display current-configuration`

支持 Huawei CLI 分页输出的自动处理。

### 配置自动备份

按照设备名称和巡检时间自动保存配置文件，例如：

```text
backup/
└── AR1/
    └── AR1_20260911_192926.txt
```

Huawei 配置备份会检查：

- 是否包含设备 `sysname`
- 是否包含配置结束标志 `return`
- 是否存在未处理的分页提示

### 网络状态自动分析

当前针对 Huawei AR1 检查：

- 接口 IP 是否符合预期
- Physical 状态是否为 up
- Protocol 状态是否为 up
- 指定目标网段是否存在于路由表
- 路由类型是否正常

示例：

```text
接口：Ethernet0/0/8
IP：192.168.100.2/24
Physical：up
Protocol：up
接口状态：NORMAL

目标网段：192.168.100.0/24
路由类型：Direct
路由状态：NORMAL
```

---

## 2. 健康评分

Huawei 设备目前采用 100 分制健康评分：

| 检查项目 | 分值 |
| --- | ---: |
| 接口 IP 正确 | 20 |
| Physical = up | 30 |
| Protocol = up | 20 |
| 目标路由存在 | 30 |
| 总分 | 100 |

状态划分：

```text
90 - 100    NORMAL
60 - 89     WARNING
0 - 59      CRITICAL
```

正常状态示例：

```text
AR1
接口状态：NORMAL
路由状态：NORMAL
健康评分：100/100
总体状态：NORMAL
```

---

## 3. 故障检测验证

项目进行了 Huawei 接口故障注入实验。

正常情况下：

```text
Ethernet0/0/8
Physical：up
Protocol：up

192.168.100.0/24 Direct

健康评分：100/100
总体状态：NORMAL
```

在 AR1 上人工执行：

```text
system-view
interface Ethernet0/0/8
shutdown
return
```

再次运行自动巡检后，系统检测到：

```text
Physical：*down
Protocol：down
目标路由不存在

接口状态：WARNING
路由状态：WARNING
健康评分：20/100
总体状态：CRITICAL
```

恢复接口：

```text
system-view
interface Ethernet0/0/8
undo shutdown
return
```

再次巡检后恢复为：

```text
健康评分：100/100
总体状态：NORMAL
```

由此形成：

```text
NORMAL
   ↓
故障注入
   ↓
CRITICAL
   ↓
故障恢复
   ↓
NORMAL
```

的完整故障检测闭环。

---

## 4. 批量巡检与异常隔离

设备信息通过 CSV 文件统一管理。

程序按设备列表逐台巡检。

即使其中某台设备发生：

- SSH 认证失败
- TCP 端口不可达
- 连接超时
- 巡检异常

也不会导致整个批量巡检任务中断。

测试中设置了一个不可达设备：

```text
BAD-TEST
127.0.0.1:2222
```

用于验证异常隔离能力。

测试结果：

```text
WIN-TEST   SUCCESS
BAD-TEST   FAILED
AR1        NORMAL
```

说明单台设备故障不会影响其他设备继续巡检。

---

## 5. 巡检报告

每次运行自动生成：

```text
reports/
├── inspection_summary_YYYYMMDD_HHMMSS.csv
└── inspection_summary_YYYYMMDD_HHMMSS.xlsx
```

Excel 报告包含：

### 巡检汇总

展示：

- 巡检时间
- 设备名称
- 管理地址
- 端口
- 设备类型
- 总体状态
- 接口
- 接口状态
- 路由状态
- 健康评分
- 异常说明及处理建议

### 统计

统计：

- 设备总数
- 正常 / 成功数量
- WARNING 数量
- CRITICAL 数量
- FAILED 数量

### 异常设备

集中展示发生异常的设备以及故障原因。

---

## 6. 项目结构

```text
network-auto-inspection/
│
├── config/
│   ├── devices.csv
│   └── devices.example.csv
│
├── src/
│   ├── main.py
│   ├── huawei_console_test.py
│   ├── huawei_parser.py
│   └── huawei_report.py
│
├── output/
├── backup/
├── logs/
├── reports/
├── docs/
│   └── images/
│       ├── ar1_normal_100.png
│       └── ar1_critical_20.png
│
├── .gitignore
├── requirements.txt
└── README.md
```

说明：

`devices.csv` 为本机真实运行配置，已通过 `.gitignore` 排除，不提交至仓库。

公开仓库提供：

```text
config/devices.example.csv
```

作为配置模板。

---

## 7. 设备配置示例

`config/devices.example.csv`：

```csv
name,host,port,username,device_type
WIN-TEST,127.0.0.1,22,netauto,windows
AR1,127.0.0.1,2000,,huawei_console
```

当前代码包含的主要设备类型：

```text
windows
huawei_console
huawei_vrp
```

其中：

- `windows`：Paramiko SSH
- `huawei_console`：eNSP Console TCP
- `huawei_vrp`：Netmiko Huawei VRP SSH 接入分支

当前实际完成验证的是 Windows SSH 和 Huawei Console TCP。

---

## 8. 环境

开发环境：

```text
Python 3.13
Windows 11
Huawei eNSP
Huawei VRP
```

主要 Python 依赖：

```text
paramiko==4.0.0
netmiko==4.7.0
openpyxl==3.1.5
```

---

## 9. 安装

创建虚拟环境：

```powershell
python -m venv .venv
```

激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

---

## 10. 配置

复制示例文件：

```powershell
Copy-Item .\config\devices.example.csv .\config\devices.csv
```

根据实际实验环境修改：

```text
host
port
username
device_type
```

---

## 11. 运行

进入项目根目录后执行：

```powershell
python .\src\main.py
```

Windows SSH 设备存在时，程序会提示：

```text
SSH password:
```

输入 Windows OpenSSH 用户密码。

程序随后自动完成：

```text
读取设备列表
    ↓
连接设备
    ↓
执行巡检命令
    ↓
保存原始输出
    ↓
配置备份
    ↓
Huawei 状态分析
    ↓
健康评分
    ↓
日志记录
    ↓
CSV 报告
    ↓
Excel 报告
```

---

## 12. 当前已完成

- [x] Windows OpenSSH 连接
- [x] Paramiko SSH 自动巡检
- [x] 多设备 CSV 管理
- [x] 单设备异常隔离
- [x] 巡检日志
- [x] 配置自动备份
- [x] CSV 报告
- [x] Excel 报告
- [x] Huawei eNSP Console TCP 自动连接
- [x] Huawei VRP CLI 自动执行
- [x] CLI 分页自动处理
- [x] Huawei 完整配置备份
- [x] 接口状态自动分析
- [x] 路由状态自动分析
- [x] 网络健康评分
- [x] NORMAL / WARNING / CRITICAL 状态判断
- [x] shutdown 故障注入验证
- [x] 故障恢复验证

---

## 13. 后续可扩展方向

以下内容属于后续规划，目前不作为已完成功能：

- 多台 Huawei 网络设备巡检
- Huawei SSH 管理链路实机验证
- VLAN 状态检测
- OSPF 邻居状态检测
- 静态路由 / 动态路由异常分析
- Linux 环境部署
- cron 定时巡检
- 邮件 / 企业微信异常告警
- Web 可视化巡检平台

---

## 14. 项目总结

该项目从基础 SSH 自动化脚本逐步扩展为一个支持 Windows 与 Huawei VRP 设备的网络自动巡检工具。

通过实际网络故障注入实验，验证了系统能够识别接口异常和路由异常，并根据设备状态自动生成健康评分、异常建议以及 Excel 巡检报告。

项目重点包括：

- Python 网络自动化
- SSH 与 TCP Socket
- Huawei VRP CLI
- 网络接口与路由状态分析
- 配置自动备份
- 异常处理
- 日志记录
- CSV / Excel 数据输出
- Git 版本管理

---

## 15. 运行效果展示

### 正常状态检测（100/100）

AR1 接口与路由状态正常时，系统自动判定为 `NORMAL`，健康评分为 `100/100`。

![AR1 Normal](docs/images/ar1_normal_100.png)

### 故障状态检测（20/100）

对 AR1 的 `Ethernet0/0/8` 执行 `shutdown` 后，系统检测到接口异常和直连路由消失，自动判定为 `CRITICAL`，健康评分下降至 `20/100`。

![AR1 Critical](docs/images/ar1_critical_20.png)

故障恢复后重新巡检，设备状态恢复为：

```text
NORMAL → CRITICAL → NORMAL
100/100 → 20/100 → 100/100
```
