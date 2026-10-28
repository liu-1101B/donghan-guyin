# TODO：安装包自动配置 eSpeak-ng

> 记录时间：2026-10-28　提出：刘佳祺　状态：待做（等项目收尾时实施）

## 目标

安装/首次启动后由项目自己把 eSpeak-ng 准备好，用户不需要手动装 MSI。
这样「三轨音频」的第一轨才真的是 eSpeak 引擎，而不是共振峰回退。

## 为什么要做

- 没装 eSpeak-ng 时，`sound_synth.py` 会静默回退到共振峰合成，第一轨听感明显变差；
- README 写的是「双引擎（eSpeak-ng + 共振峰）」，用户按 README 装完却只有单引擎，属于承诺与实现不一致；
- 打包版 `packaging/` 依赖 `download_espeak.py` 手工执行，普通用户不会跑。

## 本次实测（eSpeak-ng 1.52.0）踩到的坑

1. **官方 Windows 只有 MSI**，没有免安装 zip（近 15 个 release 仅 `.msi` / `.apk`）。
2. **`msiexec /a` 不可靠**：在受限环境返回 `1601`（无法访问 Windows Installer 服务），
   `download_espeak.py` 遇到就放弃。
3. **7z 解 MSI 是平铺 + 8.3 短名**：直接解出来叫 `espeak_ng.exe`（下划线），
   而长名 `espeak-ng.exe` 与目录结构存在 MSI 的 File / Directory / Component 表里，
   必须读表还原（`msilib`，注意 Python 3.13 起已移除该模块）。
4. **多一层产品目录**：解出的结果还套一层 `eSpeak NG/`，需要展平。
5. **找不到数据目录会直接崩**：eSpeak 1.52 在 `espeak-ng-data` 定位失败时返回
   `0xC0000005`（访问违例）而不是报错，必须显式设置 `ESPEAK_DATA_PATH`
   —— 这一条已在 `sound_synth.py:get_espeak_env()` 修好。
6. **GitHub 资源域名在国内不稳定**：直连时常 `RemoteDisconnected` / 超时，
   需要镜像回退（本次可用：`gh-proxy.com`、`ghfast.top`）。
7. **`download_espeak.py` 的 `urlretrieve` 没有超时**，网络一抖就永久挂住。

## 建议方案

**方案 A（推荐）：打包内置**
把 `espeak-ng/`（约 23 MB、443 个文件）直接打进安装包。`.gitignore` 已预留该目录，
`get_espeak_path()` 也优先找 `espeak-ng/espeak-ng.exe`，改动最小、离线可用。
代价只是安装包体积。

**方案 B：安装后下载**
Inno Setup `[Run]` 段调用下载脚本，或首次启动时后台拉取。需要：
镜像回退 → sha256 校验 → 失败可重试 → 不阻塞主界面 → 下载完成后提示重启引擎。

## 参考实现

`default-workspace\install_espeak.py` + `default-workspace\extract_msi_tree.py`
（本次已实测：从零下载 → 7z 解包 → 读 MSI 表还原目录 → 展平 → 可用 1.52.0）。

## 验收标准

- `sound_synth.ESPEAK_AVAILABLE` 为 `True`；
- 三轨音频第一轨为 eSpeak 输出（时长/波形与共振峰回退明显不同）；
- 断网环境下内置方案仍可用。

## 顺带要处理的

`packaging/sound_synth.py` 与根目录 `sound_synth.py` 已经分叉：前者有
`get_espeak()`（返回 exe 与数据目录，支持多路径）且已传 env，根目录这份是旧版。
收尾时应以其中一份为准合并，避免「打包版能响、开发版不响」这类差异。
