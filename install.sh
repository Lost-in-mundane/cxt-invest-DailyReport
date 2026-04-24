#!/usr/bin/env bash
# install.sh — 投资日报 Skills 一键安装 / 更新 / 卸载脚本
#
# 安装(或更新):
#   curl -fsSL https://github.com/Lost-in-mundane/cxt-invest-DailyReport/releases/latest/download/install.sh | bash
#   curl -fsSL https://github.com/Lost-in-mundane/cxt-invest-DailyReport/releases/latest/download/install.sh | bash -s -- --version v0.1.0
#
# 卸载:
#   bash ~/.claude/skills/.daily-report-skills-manifest/uninstall.sh
#   # 或 curl -fsSL https://.../install.sh | bash -s -- --uninstall
#
# 查看已安装位置:
#   bash ~/.claude/skills/.daily-report-skills-manifest/uninstall.sh --list
#
# 本地开发模式:
#   bash install.sh        # 脚本 + _shared/ 在同一目录时,自动走本地模式
set -euo pipefail

# ---------- 全局常量(发布前 CI 会替换 <VERSION> 占位符) ----------
REPO="Lost-in-mundane/cxt-invest-DailyReport"
DEFAULT_VERSION="latest"
# CI 打 tag 时会用 sed 把 <VERSION> 换成实际 tag,本地开发时保留 <VERSION>
BUILD_VERSION="<VERSION>"
PACKAGE_NAME="daily-report-skills"   # zip 文件名与解压后顶层目录名

# 已安装 skill 的 "家目录":存 manifest + uninstall.sh 副本
INSTALL_META_DIR="$HOME/.claude/skills/.daily-report-skills-manifest"
MANIFEST_FILE="$INSTALL_META_DIR/installed.manifest"

# ---------- 颜色 ----------
if [[ -t 1 ]]; then
  C_G=$'\033[0;32m'; C_Y=$'\033[0;33m'; C_R=$'\033[0;31m'; C_B=$'\033[0;34m'; C_N=$'\033[0m'
else
  C_G=""; C_Y=""; C_R=""; C_B=""; C_N=""
fi

info()  { echo "${C_B}ℹ${C_N}  $*"; }
ok()    { echo "${C_G}✓${C_N}  $*"; }
warn()  { echo "${C_Y}⚠${C_N}  $*"; }
err()   { echo "${C_R}✗${C_N}  $*" >&2; }

# ---------- 参数 ----------
MODE="install"
TARGET_DIR=""
VERSION="$DEFAULT_VERSION"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uninstall) MODE="uninstall"; shift ;;
    --list)      MODE="list"; shift ;;
    --dir)       TARGET_DIR="$2"; shift 2 ;;
    --version)   VERSION="$2"; shift 2 ;;
    -h|--help)
      grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -25
      exit 0 ;;
    *) err "未知参数: $1"; exit 1 ;;
  esac
done

# ---------- 决定源目录:本地 or 远程 ----------
# 优先看脚本"兄弟目录"有没有 _shared/(本地开发 / 已解压场景)
SCRIPT_DIR=""
if [[ -f "${BASH_SOURCE[0]:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || SCRIPT_DIR=""
fi

SRC_DIR=""
DOWNLOAD_TMP=""
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/_shared/fetch.py" ]]; then
  SRC_DIR="$SCRIPT_DIR"
  info "本地模式: 源目录 = $SRC_DIR"
else
  # 远程模式:install/uninstall 都可能走这里;卸载和 list 不需要源码
  if [[ "$MODE" == "install" ]]; then
    command -v curl >/dev/null 2>&1 || { err "需要 curl"; exit 1; }
    command -v unzip >/dev/null 2>&1 || { err "需要 unzip"; exit 1; }

    if [[ "$VERSION" == "latest" ]]; then
      ZIP_URL="https://github.com/$REPO/releases/latest/download/$PACKAGE_NAME.zip"
    else
      ZIP_URL="https://github.com/$REPO/releases/download/$VERSION/$PACKAGE_NAME.zip"
    fi

    DOWNLOAD_TMP="$(mktemp -d 2>/dev/null || mktemp -d -t drs)"
    trap 'rm -rf "$DOWNLOAD_TMP"' EXIT

    info "远程模式: 下载 $ZIP_URL"
    if ! curl -fsSL "$ZIP_URL" -o "$DOWNLOAD_TMP/pkg.zip"; then
      err "下载失败: $ZIP_URL"
      err "检查网络,或 --version 指定的 tag 是否存在"
      exit 1
    fi

    unzip -q "$DOWNLOAD_TMP/pkg.zip" -d "$DOWNLOAD_TMP"
    SRC_DIR="$DOWNLOAD_TMP/$PACKAGE_NAME"
    if [[ ! -d "$SRC_DIR" ]]; then
      err "解压后找不到 $SRC_DIR"
      err "zip 结构可能变化,请联系维护者"
      exit 1
    fi
    ok "下载解压完成"
  fi
fi

SKILLS=(daily-report daily-report-setup daily-report-reset)
SHARED_FETCH="fetch.py"
SHARED_RENDER="render.py"

# ---------- 探测 agent skill 目录 ----------
detect_skill_dirs() {
  local dirs=()
  [[ -d "$HOME/.claude" ]]    && dirs+=("$HOME/.claude/skills")
  [[ -d "$HOME/.codebuddy" ]] && dirs+=("$HOME/.codebuddy/skills")
  [[ -d "$HOME/.cursor" ]]    && dirs+=("$HOME/.cursor/skills")
  printf '%s\n' "${dirs[@]}"
}

# ---------- 安装到某个 skills 目录 ----------
install_to() {
  local dst="$1"
  mkdir -p "$dst"

  for skill in "${SKILLS[@]}"; do
    local src="$SRC_DIR/$skill"
    local tgt="$dst/$skill"
    if [[ ! -d "$src" ]]; then
      err "源目录不存在: $src"; return 1
    fi
    if [[ -d "$tgt" ]]; then
      local bak="${tgt}.bak.$(date +%s)"
      mv "$tgt" "$bak"
      warn "已存在 $tgt,备份到 $bak"
    fi
    cp -R "$src" "$tgt"
  done

  mkdir -p "$dst/daily-report/scripts"
  cp "$SRC_DIR/_shared/$SHARED_FETCH"  "$dst/daily-report/scripts/$SHARED_FETCH"
  cp "$SRC_DIR/_shared/$SHARED_RENDER" "$dst/daily-report/scripts/$SHARED_RENDER"
  chmod +x "$dst/daily-report/scripts/$SHARED_FETCH" "$dst/daily-report/scripts/$SHARED_RENDER"

  mkdir -p "$dst/daily-report-setup/scripts"
  cp "$SRC_DIR/_shared/$SHARED_FETCH" "$dst/daily-report-setup/scripts/$SHARED_FETCH"
  chmod +x "$dst/daily-report-setup/scripts/$SHARED_FETCH"

  mkdir -p "$INSTALL_META_DIR"
  for skill in "${SKILLS[@]}"; do
    echo "$dst/$skill"
  done >> "$MANIFEST_FILE"

  ok "已安装到 $dst"
}

# ---------- 把 install.sh 自己拷一份到 meta 目录当 uninstall.sh ----------
install_uninstall_shortcut() {
  mkdir -p "$INSTALL_META_DIR"
  local target="$INSTALL_META_DIR/uninstall.sh"
  # 源:本地模式用当前脚本文件,远程模式用下载下来的 install.sh
  local src_script=""
  if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/install.sh" ]]; then
    src_script="$SCRIPT_DIR/install.sh"
  elif [[ -f "$SRC_DIR/install.sh" ]]; then
    src_script="$SRC_DIR/install.sh"
  else
    # 最后兜底:自己当前的 $0,可能是 /dev/fd/63(pipe) 拷不动,忽略
    return 0
  fi
  cp "$src_script" "$target" 2>/dev/null || return 0
  chmod +x "$target" 2>/dev/null || true
}

# ---------- 卸载 ----------
do_uninstall() {
  if [[ ! -f "$MANIFEST_FILE" ]]; then
    warn "未找到安装记录($MANIFEST_FILE),没什么可卸载的"
    return 0
  fi
  local count=0
  local unique_paths
  unique_paths="$(sort -u "$MANIFEST_FILE")"
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if [[ -d "$path" ]]; then
      rm -rf "$path"
      ok "已删除 $path"
      count=$((count + 1))
    fi
  done <<< "$unique_paths"
  rm -f "$MANIFEST_FILE"
  # 清理 meta 目录(含 uninstall.sh 自己);允许失败(如果用户还开着脚本)
  rm -rf "$INSTALL_META_DIR" 2>/dev/null || true
  ok "共卸载 $count 个 skill 目录"
  info "画像数据仍保留在 ~/.daily-report/(需自行删除)"
}

# ---------- list ----------
do_list() {
  if [[ -f "$MANIFEST_FILE" ]]; then
    echo "根据 manifest,以下位置已安装:"
    sort -u "$MANIFEST_FILE"
  else
    echo "未找到安装记录($MANIFEST_FILE)"
  fi
}

# ---------- Python 依赖检查(软) ----------
check_python_deps() {
  command -v python3 >/dev/null 2>&1 || { warn "未检测到 python3;日报生成会降级到 WebSearch(慢)"; return; }
  # 版本检查:最低 3.9
  local pyver
  pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "")"
  if [[ -n "$pyver" ]]; then
    local major minor
    major="${pyver%.*}"
    minor="${pyver#*.}"
    if [[ "$major" -lt 3 || ( "$major" -eq 3 && "$minor" -lt 9 ) ]]; then
      warn "Python $pyver 版本较低,建议 >= 3.9(当前可能部分 akshare 接口不支持)"
    fi
  fi
  local missing=()
  for m in akshare yfinance; do
    python3 -c "import $m" 2>/dev/null || missing+=("$m")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    warn "建议安装: pip3 install ${missing[*]}"
    warn "不装也能跑,但行情数据会退化到 WebSearch,体验慢很多"
  else
    ok "Python 依赖齐全(akshare + yfinance)"
  fi
}

# ---------- 主流程 ----------
case "$MODE" in
  list)      do_list; exit 0 ;;
  uninstall) do_uninstall; exit 0 ;;
  install)   ;;
esac

info "cxt-invest-DailyReport 安装器(版本: ${BUILD_VERSION})"

# 决定装到哪些位置
TARGETS=()
if [[ -n "$TARGET_DIR" ]]; then
  TARGETS=("$TARGET_DIR")
else
  while IFS= read -r d; do TARGETS+=("$d"); done < <(detect_skill_dirs)
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  warn "没有探测到任何 Agent 的 skill 目录"
  warn "默认安装到 $HOME/.claude/skills/(可用 --dir 指定其他路径)"
  TARGETS=("$HOME/.claude/skills")
fi

info "将安装到以下位置:"
for t in "${TARGETS[@]}"; do echo "  - $t"; done

# 清空旧 manifest(重装覆盖)
if [[ -f "$MANIFEST_FILE" ]]; then
  : > "$MANIFEST_FILE"
fi

for t in "${TARGETS[@]}"; do
  install_to "$t"
done

# 拷 uninstall.sh 到 meta 目录
install_uninstall_shortcut

# 初始化画像目录
mkdir -p "$HOME/.daily-report"
ok "已创建画像目录: ~/.daily-report/"

# 依赖检查
check_python_deps

echo
ok "全部完成。重启你的 Agent(Claude Code / CodeBuddy),新会话里说 '设置日报' 开始配置。"
echo
info "卸载:  bash $INSTALL_META_DIR/uninstall.sh"
info "查看:  bash $INSTALL_META_DIR/uninstall.sh --list"
info "更新:  重新跑一次本条 curl 命令即可"
