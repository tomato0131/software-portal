"""
企业内网软件分发平台
Apple风格设计 | Flask + SQLite | 部门权限控制
"""

import os
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, jsonify, abort, Response
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ─── App Config ───────────────────────────────────────────
app = Flask(__name__)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30},  # SQLite busy_timeout 30s
    'pool_pre_ping': True,
}
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
app.config['ICON_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads', 'icons')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB max upload

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['ICON_FOLDER'], exist_ok=True)

ALLOWED_ICON_EXT = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico', 'webp'}

# ─── Auto Icon Generation ─────────────────────────────────

# 常见软件品牌色映射（主色, 渐变副色, 显示字符）
BRAND_COLORS = {
    '谷歌浏览器':     ((66, 133, 244), (40, 100, 220), 'G'),
    'google chrome':  ((66, 133, 244), (40, 100, 220), 'G'),
    '360安全卫士':    ((0, 168, 80), (0, 130, 60), '360'),
    '360浏览器':      ((0, 168, 80), (0, 130, 60), '360'),
    'wps office':     ((210, 60, 50), (170, 40, 35), 'W'),
    'wps':            ((210, 60, 50), (170, 40, 35), 'W'),
    '企业微信':       ((7, 193, 96), (5, 155, 75), '企'),
    '微信':           ((7, 193, 96), (5, 155, 75), '微'),
    '钉钉':           ((0, 160, 230), (0, 125, 185), '钉'),
    '腾讯会议':       ((0, 130, 250), (0, 100, 210), '会'),
    '瞩目会议':       ((0, 130, 250), (0, 100, 210), '瞩'),
    'enues':          ((30, 60, 120), (20, 40, 90), 'En'),
    'aone':           ((255, 120, 0), (210, 95, 0), 'Ao'),
    'xmind':          ((240, 70, 55), (200, 50, 40), 'Xm'),
    'everything':     ((255, 180, 0), (210, 145, 0), 'Ev'),
    'winrar':         ((120, 80, 180), (90, 55, 145), 'Wr'),
    '压缩软件winrar': ((120, 80, 180), (90, 55, 145), 'Wr'),
    '7-zip':          ((80, 140, 50), (55, 110, 30), '7z'),
    '压缩软件7-zip':  ((80, 140, 50), (55, 110, 30), '7z'),
    '火绒杀毒软件':   ((0, 190, 170), (0, 155, 140), '火'),
    '搜狗拼音输入法': ((255, 140, 0), (210, 110, 0), '拼'),
    '搜狗五笔输入法': ((255, 100, 0), (210, 75, 0), '五'),
    '量子密信':       ((60, 80, 180), (40, 55, 140), '量'),
    '云镜终端安全防护系统': ((40, 70, 140), (25, 45, 100), '云'),
    'cme':            ((0, 90, 170), (0, 65, 130), 'CME'),
    'geek':           ((60, 70, 80), (35, 45, 55), 'Gk'),
}

# 通用渐变方案（按软件名 hash 落选品牌色后使用）
_FALLBACK_GRADIENTS = [
    ((66, 133, 244), (40, 100, 220)),
    ((52, 199, 89), (30, 160, 60)),
    ((255, 149, 0), (220, 120, 0)),
    ((175, 82, 222), (130, 50, 200)),
    ((255, 59, 48), (220, 30, 20)),
    ((0, 199, 190), (0, 160, 155)),
    ((255, 45, 85), (220, 20, 60)),
    ((88, 86, 214), (60, 50, 180)),
    ((255, 179, 64), (220, 145, 30)),
    ((100, 120, 140), (70, 90, 110)),
]


def _superellipse_mask(size, corner_ratio=0.18):
    """生成 Apple 风格 squircle（超椭圆）遮罩"""
    import math
    n = 5  # 超椭圆指数，越大越接近矩形；Apple 约为 5
    mask = Image.new('L', (size, size), 0)
    r = int(size * corner_ratio)
    cx, cy = size / 2, size / 2
    a = cx  # 半长轴
    b = cy  # 半短轴
    for y in range(size):
        for x in range(size):
            dx = abs(x - cx) / a
            dy = abs(y - cy) / b
            # 超椭圆方程: |x/a|^n + |y/b|^n <= 1
            val = (dx ** n + dy ** n) ** (1 / n)
            if val <= 1.0:
                # 柔和抗锯齿边缘
                edge = max(0, min(1, (1.0 - val) * a * 0.8))
                mask.putpixel((x, y), int(edge * 255))
    return mask


def generate_auto_icon(name):
    """根据软件名称自动生成白色背景 Apple 风格 squircle 图标 PNG"""
    if not HAS_PIL:
        return None
    import math

    size = 256
    key = name.strip().lower()

    # 查品牌色（仅用于文字颜色）
    brand = None
    for bname, bval in BRAND_COLORS.items():
        if bname.lower() == key or key.startswith(bname.lower()):
            brand = bval
            break

    if brand:
        (r1, g1, b1), (r2, g2, b2), char = brand
        # 品牌色用于文字，背景白色
        text_r, text_g, text_b = r1, g1, b1
    else:
        idx = sum(ord(c) for c in name) % len(_FALLBACK_GRADIENTS)
        (r1, g1, b1), (r2, g2, b2) = _FALLBACK_GRADIENTS[idx]
        char = name[0].upper() if name else '?'
        text_r, text_g, text_b = r1, g1, b1

    # ── 1) 白色背景 ──
    bg = Image.new('RGB', (size, size), (255, 255, 255))

    # ── 2) Squircle 遮罩 ──
    mask = _superellipse_mask(size, corner_ratio=0.22)

    # ── 3) 合成：透明背景 + squircle 图标 ──
    final = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    final.paste(bg, (0, 0), mask)

    # ── 4) 绘制文字（品牌色） ──
    if len(char) <= 1:
        font_size = 120
    elif len(char) == 2:
        font_size = 100
    elif len(char) == 3:
        font_size = 72
    else:
        font_size = 56

    try:
        font = ImageFont.truetype('/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf', font_size)
    except Exception:
        try:
            font = ImageFont.truetype('/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf', font_size)
        except Exception:
            font = ImageFont.load_default()

    draw = ImageDraw.Draw(final)
    # 居中
    dummy_img = Image.new('RGBA', (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    bbox = dummy_draw.textbbox((0, 0), char, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (size - tw) / 2 - bbox[0]
    ty = (size - th) / 2 - bbox[1]

    # 文字阴影
    draw.text((tx + 1, ty + 2), char, fill=(0, 0, 0, 25), font=font)
    # 品牌色文字
    draw.text((tx, ty), char, fill=(text_r, text_g, text_b, 230), font=font)

    # ── 5) 保存 ──
    icon_name = f'{uuid.uuid4().hex}.png'
    icon_path = os.path.join(app.config['ICON_FOLDER'], icon_name)
    final.save(icon_path, 'PNG')
    return icon_name


db = SQLAlchemy(app)

# 自动迁移：检查并添加新列（首次运行时执行）
def _auto_migrate():
    import sqlite3
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 检查 group_id 列是否存在
    cursor.execute("PRAGMA table_info(software)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'group_id' not in columns:
        cursor.execute("ALTER TABLE software ADD COLUMN group_id VARCHAR(64)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_software_group_id ON software (group_id)")
        # 为现有软件生成 group_id
        cursor.execute("SELECT id, name FROM software WHERE group_id IS NULL")
        for row in cursor.fetchall():
            import uuid
            cursor.execute("UPDATE software SET group_id = ? WHERE id = ?", (uuid.uuid4().hex, row[0]))
        print("Migration: group_id column added")
    if 'is_latest' not in columns:
        cursor.execute("ALTER TABLE software ADD COLUMN is_latest BOOLEAN DEFAULT 1")
        print("Migration: is_latest column added")
    if 'changelog' not in columns:
        cursor.execute("ALTER TABLE software ADD COLUMN changelog TEXT")
        print("Migration: changelog column added")
    conn.commit()
    conn.close()

try:
    _auto_migrate()
except Exception as e:
    print(f"Migration warning: {e}")


# SQLite WAL mode: set via engine connect event
from sqlalchemy import event

def set_sqlite_pragmas(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA busy_timeout=30000')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.execute('PRAGMA cache_size=-64000')  # 64MB cache
    cursor.close()

with app.app_context():
    event.listen(db.engine, 'connect', set_sqlite_pragmas)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录访问此页面'


# ─── Models ────────────────────────────────────────────────
class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    users = db.relationship('User', backref='department', lazy='dynamic')

    def __repr__(self):
        return f'<Department {self.name}>'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(100))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def dept_name(self):
        return self.department.name if self.department else '未分配'


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(100), default='folder')
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    software_list = db.relationship('Software', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.name}>'


class Software(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    version = db.Column(db.String(50))
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    filename = db.Column(db.String(500))        # stored filename
    original_name = db.Column(db.String(500))    # user's original filename
    file_size = db.Column(db.Integer)            # bytes
    platform = db.Column(db.String(50))          # Windows/macOS/Linux/跨平台
    icon = db.Column(db.String(500))              # 自定义图标文件名
    download_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 版本管理
    group_id = db.Column(db.String(64), index=True)  # 同名软件共享一个 group_id
    is_latest = db.Column(db.Boolean, default=True)   # 是否为最新版本
    changelog = db.Column(db.Text)                    # 版本更新日志

    @property
    def size_display(self):
        if not self.file_size:
            return '—'
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.file_size < 1024:
                return f'{self.file_size:.1f} {unit}'
            self.file_size /= 1024
        return f'{self.file_size:.1f} TB'


class Permission(db.Model):
    """部门-分类权限：控制哪个部门能看到哪个分类"""
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))

    __table_args__ = (db.UniqueConstraint('department_id', 'category_id'),)

    department = db.relationship('Department', backref='permissions')
    category = db.relationship('Category', backref='permissions')


class DownloadLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    software_id = db.Column(db.Integer, db.ForeignKey('software.id'))
    downloaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))

    user = db.relationship('User', backref='downloads')
    software = db.relationship('Software', backref='downloads')


# ─── Login Manager ─────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ─── Decorators ────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─── Helper ────────────────────────────────────────────────
def get_allowed_category_ids(user):
    """获取用户有权限查看的分类ID列表 - 所有用户可看所有分类"""
    return [c.id for c in Category.query.order_by(Category.sort_order).all()]


# 缓存分类ID列表，避免每次请求都查数据库
_category_cache = {'ids': None, 'time': 0}

def get_cached_category_ids():
    """缓存5秒的分类ID列表"""
    import time
    now = time.time()
    if _category_cache['ids'] is None or (now - _category_cache['time']) > 5:
        _category_cache['ids'] = get_allowed_category_ids(None)
        _category_cache['time'] = now
    return _category_cache['ids']


def get_accessible_software(user, category_id=None, search=None, platform=None):
    """获取用户可访问的软件列表"""
    allowed_ids = get_cached_category_ids()
    query = Software.query.filter(Software.category_id.in_(allowed_ids))
    if category_id:
        query = query.filter_by(category_id=category_id)
    if search:
        search_filter = Software.name.contains(search) | Software.description.contains(search) | Software.version.contains(search)
        query = query.filter(search_filter)
    if platform:
        if platform == 'windows':
            query = query.filter(Software.platform.in_(['Windows', 'Windows/macOS', '跨平台']))
        elif platform == 'macos':
            query = query.filter(Software.platform.in_(['macOS', 'Windows/macOS', '跨平台']))
        elif platform == 'xinchuang':
            query = query.filter(Software.platform.in_(['信创操作系统', '跨平台']))
    return query.order_by(Software.download_count.desc()).all()


# ─── Auth Routes ───────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user)
            flash('登录成功', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('用户名或密码错误', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'success')
    return redirect(url_for('login'))


# ─── Main Routes ───────────────────────────────────────────
@app.route('/')
@login_required
def index():
    allowed_ids = get_cached_category_ids()
    categories = Category.query.filter(Category.id.in_(allowed_ids)).order_by(Category.sort_order).all()
    search = request.args.get('q', '')
    cat_id = request.args.get('category', type=int)
    platform = request.args.get('platform', '')
    all_software = get_accessible_software(current_user, category_id=cat_id, search=search, platform=platform)

    # 按名称分组：同名软件只显示最新版本，但保留所有版本供切换
    from collections import OrderedDict
    software_groups = OrderedDict()
    for sw in all_software:
        key = sw.group_id or str(sw.id)
        if key not in software_groups:
            software_groups[key] = []
        software_groups[key].append(sw)

    # 每组取最新版作为主显示，其余作为版本列表
    software_list = []
    for group_id, versions in software_groups.items():
        # 按 created_at 降序排列，最新的在前
        versions.sort(key=lambda x: x.created_at, reverse=True)
        latest = versions[0]
        latest.is_latest = True
        # 将版本列表信息附加到最新版对象上
        latest._all_versions = versions
        software_list.append(latest)

    # 搜索高亮关键词
    search_keyword = search if search else ''

    # 下载统计：按分类汇总
    total_downloads = sum(sw.download_count for sw in software_list)
    cat_stats = []
    for cat in categories:
        sw_in_cat = [s for s in software_list if s.category_id == cat.id]
        dl_count = sum(s.download_count for s in sw_in_cat)
        cat_stats.append({'name': cat.name, 'icon': cat.icon, 'count': len(sw_in_cat), 'downloads': dl_count})

    return render_template('index.html',
                           categories=categories,
                           software_list=software_list,
                           current_category=cat_id,
                           current_platform=platform,
                           search=search,
                           search_keyword=search_keyword,
                           total_downloads=total_downloads,
                           total_software=len(software_list),
                           cat_stats=cat_stats)


@app.route('/download/<int:software_id>')
@login_required
def download_file(software_id):
    sw = db.session.get(Software, software_id)
    if not sw:
        abort(404)
    # Permission check
    allowed_ids = get_cached_category_ids()
    if sw.category_id not in allowed_ids:
        abort(403)
    # Log
    log = DownloadLog(
        user_id=current_user.id,
        software_id=software_id,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    sw.download_count += 1
    db.session.commit()
    # Use Nginx X-Accel-Redirect to send file directly
    # This releases Gunicorn worker immediately instead of blocking it
    response = Response()
    response.headers['X-Accel-Redirect'] = '/internal-download/' + sw.filename
    response.headers['Content-Type'] = 'application/octet-stream'
    from urllib.parse import quote
    encoded = quote(sw.original_name)
    response.headers["Content-Disposition"] = "attachment; filename=\"" + encoded + "\"; filename*=UTF-8''" + encoded
    return response




# ─── Analytics: IP归属地 + 高频检测 ───────────────────────
import urllib.request, json, time as _time

# IP归属地缓存：{ip: {"location": "城市", "ts": timestamp}}
_ip_location_cache = {}
_ip_cache_ttl = 86400  # 缓存24小时

def _is_internal_ip(ip):
    """判断是否内网IP"""
    if not ip or ip == '127.0.0.1' or ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
        return True
    return False

def get_ip_locations(ips):
    """批量查询IP归属地（ip-api.com 免费API，每次最多100个）
    返回 {ip: "城市, 省份, 国家"} 
    """
    # 过滤已缓存且未过期的IP
    now = _time.time()
    unique_ips = list(set(ips))
    to_query = []
    result = {}

    for ip in unique_ips:
        if _is_internal_ip(ip):
            result[ip] = '内网地址'
            continue
        cached = _ip_location_cache.get(ip)
        if cached and (now - cached['ts']) < _ip_cache_ttl:
            result[ip] = cached['location']
        else:
            to_query.append(ip)

    # 批量查询（每次最多100个）
    while to_query:
        batch = to_query[:100]
        to_query = to_query[100:]
        try:
            data = json.dumps([{"query": ip, "fields": "query,country,regionName,city,status"} for ip in batch]).encode()
            req = urllib.request.Request(
                "http://ip-api.com/batch",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                items = json.loads(resp.read().decode())
                for item in items:
                    ip = item.get('query', '')
                    if item.get('status') == 'success':
                        parts = [p for p in [item.get('city'), item.get('regionName'), item.get('country')] if p]
                        loc = ', '.join(parts) if parts else '未知'
                    else:
                        loc = '查询失败'
                    result[ip] = loc
                    _ip_location_cache[ip] = {'location': loc, 'ts': now}
        except Exception as e:
            # 查询失败时给默认值
            for ip in batch:
                if ip not in result:
                    result[ip] = '查询超时'
            print(f"IP batch query failed: {e}")

    return result


def get_high_frequency_ips(threshold=8, minutes=30):
    """检测短时间内高频访问的IP（疑似攻击）
    同时检测IP维度和用户维度的异常
    返回 [{ip, count, first_time, last_time}] 按次数降序
    """
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(minutes=minutes)

    # 查询最近N分钟内的下载记录，按IP分组统计
    rows = db.session.query(
        DownloadLog.ip_address,
        db.func.count(DownloadLog.id).label('cnt'),
        db.func.min(DownloadLog.downloaded_at).label('first_at'),
        db.func.max(DownloadLog.downloaded_at).label('last_at')
    ).filter(
        DownloadLog.downloaded_at >= since
    ).group_by(
        DownloadLog.ip_address
    ).having(
        db.func.count(DownloadLog.id) >= threshold
    ).order_by(
        db.func.count(DownloadLog.id).desc()
    ).all()

    return [{
        'ip': row.ip_address,
        'count': row.cnt,
        'first_time': row.first_at,
        'last_time': row.last_at
    } for row in rows]


# ─── Admin Analytics Route ────────────────────────────────
@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    from datetime import datetime, timedelta
    from sqlalchemy import func

    # 1. 最近24小时下载统计（按小时）
    now = datetime.utcnow()
    hourly_stats = []
    for i in range(23, -1, -1):
        hour_start = now - timedelta(hours=i)
        hour_start = hour_start.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        count = db.session.query(func.count(DownloadLog.id)).filter(
            DownloadLog.downloaded_at >= hour_start,
            DownloadLog.downloaded_at < hour_end
        ).scalar()
        hourly_stats.append({
            'hour': hour_start.strftime('%H:%M'),
            'count': count or 0
        })

    # 2. 最近50条下载记录（去重：同用户+同软件在1分钟内只保留1条）
    all_logs = DownloadLog.query.order_by(DownloadLog.downloaded_at.desc()).limit(200).all()
    seen = set()
    recent_logs = []
    for log in all_logs:
        key = (log.user_id, log.software_id, log.downloaded_at.strftime('%Y-%m-%d %H:%M'))
        if key not in seen:
            seen.add(key)
            recent_logs.append(log)
        if len(recent_logs) >= 50:
            break
    ips_to_query = [log.ip_address for log in recent_logs if not _is_internal_ip(log.ip_address)]
    ip_locations = get_ip_locations(ips_to_query) if ips_to_query else {}

    recent_downloads_data = []
    for log in recent_logs:
        ip = log.ip_address
        location = '内网地址' if _is_internal_ip(ip) else ip_locations.get(ip, '查询中...')
        recent_downloads_data.append({
            'user': log.user.display_name or log.user.username if log.user else '未知',
            'software': log.software.name if log.software else '已删除',
            'time': log.downloaded_at.strftime('%Y-%m-%d %H:%M:%S'),
            'ip': ip,
            'location': location
        })

    # 3. 热门软件排行（最近7天 Top 10）
    week_ago = now - timedelta(days=7)
    top_software = db.session.query(
        Software.name,
        func.count(DownloadLog.id).label('dl_count')
    ).join(DownloadLog, Software.id == DownloadLog.software_id).filter(
        DownloadLog.downloaded_at >= week_ago
    ).group_by(Software.name).order_by(
        func.count(DownloadLog.id).desc()
    ).limit(10).all()

    # 4. 高频IP访问预警（30分钟内超过8次）
    high_freq_ips = get_high_frequency_ips(threshold=8, minutes=30)
    # 为高频IP也查询归属地
    hf_ips_to_query = [item['ip'] for item in high_freq_ips if not _is_internal_ip(item['ip'])]
    if hf_ips_to_query:
        hf_locations = get_ip_locations(hf_ips_to_query)
        for item in high_freq_ips:
            ip = item['ip']
            item['location'] = '内网地址' if _is_internal_ip(ip) else hf_locations.get(ip, '查询中...')
            item['first_time_str'] = item['first_time'].strftime('%H:%M:%S') if item['first_time'] else ''
            item['last_time_str'] = item['last_time'].strftime('%H:%M:%S') if item['last_time'] else ''

    # 5. 下载来源城市分布
    city_stats = {}
    for item in recent_downloads_data:
        loc = item['location']
        if loc and loc != '内网地址' and loc != '查询中...' and loc != '查询失败' and loc != '查询超时':
            # 取城市名（第一个逗号前）
            city = loc.split(',')[0].strip() if ',' in loc else loc
            city_stats[city] = city_stats.get(city, 0) + 1
    city_rank = sorted(city_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    return render_template('admin/analytics.html',
                           hourly_stats=hourly_stats,
                           recent_downloads=recent_downloads_data,
                           top_software=top_software,
                           high_freq_ips=high_freq_ips,
                           city_rank=city_rank)


# ─── Admin Routes ──────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = {
        'users': User.query.count(),
        'software': Software.query.count(),
        'categories': Category.query.count(),
        'downloads': DownloadLog.query.count(),
    }
    recent_downloads = DownloadLog.query.order_by(DownloadLog.downloaded_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html', stats=stats, recent_downloads=recent_downloads)


# --- Software Admin ---
@app.route('/admin/software', methods=['GET', 'POST'])
@admin_required
def admin_software():
    if request.method == 'POST':
        name = request.form.get('name')
        version = request.form.get('version')
        description = request.form.get('description')
        category_id = request.form.get('category_id', type=int)
        platform = request.form.get('platform')
        file = request.files.get('file')

        sw = Software(name=name, version=version, description=description,
                      category_id=category_id, platform=platform)
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1]
            stored_name = f'{uuid.uuid4().hex}{ext}'
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
            file.save(file_path)
            sw.filename = stored_name
            sw.original_name = secure_filename(file.filename)
            sw.file_size = os.path.getsize(file_path)

        # 处理图标：优先用户上传，否则自动生成
        icon_file = request.files.get('icon')
        icon_set = False
        if icon_file and icon_file.filename:
            icon_ext = os.path.splitext(icon_file.filename)[1].lower().lstrip('.')
            if icon_ext in ALLOWED_ICON_EXT:
                icon_name = f'{uuid.uuid4().hex}.{icon_ext}'
                icon_path = os.path.join(app.config['ICON_FOLDER'], icon_name)
                icon_file.save(icon_path)
                sw.icon = icon_name
                icon_set = True
        if not icon_set:
            sw.icon = generate_auto_icon(name)

        db.session.add(sw)
        db.session.commit()
        flash('软件已添加', 'success')
        return redirect(url_for('admin_dashboard'))

    software_list = Software.query.order_by(Software.created_at.desc()).all()
    categories = Category.query.order_by(Category.sort_order).all()
    upload_folder = app.config['UPLOAD_FOLDER']
    return render_template('admin/software.html', software_list=software_list, categories=categories, upload_folder=upload_folder)


@app.route('/admin/software/edit/<int:id>', methods=['POST'])
@admin_required
def admin_software_edit(id):
    sw = db.session.get(Software, id)
    if not sw:
        abort(404)
    sw.name = request.form.get('name', sw.name)
    sw.version = request.form.get('version', sw.version)
    sw.description = request.form.get('description', sw.description)
    sw.category_id = request.form.get('category_id', type=int) or sw.category_id
    sw.platform = request.form.get('platform', sw.platform)

    file = request.files.get('file')
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1]
        stored_name = f'{uuid.uuid4().hex}{ext}'
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
        file.save(file_path)
        # remove old file
        if sw.filename:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], sw.filename)
            if os.path.exists(old_path):
                os.remove(old_path)
        sw.filename = stored_name
        sw.original_name = secure_filename(file.filename)
        sw.file_size = os.path.getsize(file_path)

    # 处理图标：优先用户上传
    icon_file = request.files.get('icon')
    if icon_file and icon_file.filename:
        icon_ext = os.path.splitext(icon_file.filename)[1].lower().lstrip('.')
        if icon_ext in ALLOWED_ICON_EXT:
            icon_name = f'{uuid.uuid4().hex}.{icon_ext}'
            icon_path = os.path.join(app.config['ICON_FOLDER'], icon_name)
            icon_file.save(icon_path)
            # 删除旧图标
            if sw.icon:
                old_icon = os.path.join(app.config['ICON_FOLDER'], sw.icon)
                if os.path.exists(old_icon):
                    os.remove(old_icon)
            sw.icon = icon_name
    elif not sw.icon:
        # 没上传且原来也没有图标，自动生成
        sw.icon = generate_auto_icon(sw.name or 'App')

    db.session.commit()
    flash('软件已更新', 'success')
    return redirect(url_for('admin_dashboard'))




@app.route('/admin/software/new-version/<int:software_id>', methods=['GET', 'POST'])
@admin_required
def admin_new_version(software_id):
    """为已有软件添加新版本"""
    sw = db.session.get(Software, software_id)
    if not sw:
        abort(404)

    if request.method == 'POST':
        version = request.form.get('version')
        changelog = request.form.get('changelog', '')
        file = request.files.get('file')
        platform = request.form.get('platform', sw.platform)

        if not (file and file.filename):
            flash('请上传安装包文件', 'error')
            return redirect(url_for('admin_new_version', software_id=software_id))

        # 保存新版本文件
        ext = os.path.splitext(file.filename)[1]
        stored_name = f'{uuid.uuid4().hex}{ext}'
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
        file.save(file_path)

        # 将旧版本标记为非最新
        group_id = sw.group_id or str(sw.id)
        if not sw.group_id:
            sw.group_id = group_id
            db.session.commit()

        Software.query.filter_by(group_id=group_id).update({'is_latest': False})

        # 创建新版本记录
        new_sw = Software(
            name=sw.name,
            version=version,
            description=sw.description,
            category_id=sw.category_id,
            filename=stored_name,
            original_name=secure_filename(file.filename),
            file_size=os.path.getsize(file_path),
            platform=platform,
            icon=sw.icon,
            group_id=group_id,
            is_latest=True,
            changelog=changelog
        )
        db.session.add(new_sw)
        db.session.commit()
        flash(f'{sw.name} 新版本 {version} 已添加', 'success')
        return redirect(url_for('admin_software'))

    # GET: 显示添加新版本页面
    return render_template('admin/new_version.html', software=sw)

@app.route('/admin/software/delete/<int:id>', methods=['POST'])
@admin_required
def admin_software_delete(id):
    sw = db.session.get(Software, id)
    if not sw:
        abort(404)
    if sw.filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], sw.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    if sw.icon:
        old_icon = os.path.join(app.config['ICON_FOLDER'], sw.icon)
        if os.path.exists(old_icon):
            os.remove(old_icon)
    db.session.delete(sw)
    db.session.commit()
    flash('软件已删除', 'success')
    return redirect(url_for('admin_software'))


# --- Category Admin ---
@app.route('/admin/categories', methods=['GET', 'POST'])
@admin_required
def admin_categories():
    if request.method == 'POST':
        name = request.form.get('name')
        icon = request.form.get('icon', 'folder')
        description = request.form.get('description')
        sort_order = request.form.get('sort_order', type=int) or 0
        cat = Category(name=name, icon=icon, description=description, sort_order=sort_order)
        db.session.add(cat)
        db.session.commit()
        flash('分类已添加', 'success')
        return redirect(url_for('admin_categories'))
    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('admin/categories.html', categories=categories)


@app.route('/admin/categories/edit/<int:id>', methods=['POST'])
@admin_required
def admin_categories_edit(id):
    cat = db.session.get(Category, id)
    if not cat:
        abort(404)
    cat.name = request.form.get('name', cat.name)
    cat.icon = request.form.get('icon', cat.icon)
    cat.description = request.form.get('description', cat.description)
    cat.sort_order = request.form.get('sort_order', type=int) or cat.sort_order
    db.session.commit()
    flash('分类已更新', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/categories/delete/<int:id>', methods=['POST'])
@admin_required
def admin_categories_delete(id):
    cat = db.session.get(Category, id)
    if not cat:
        abort(404)
    if cat.software_list.count() > 0:
        flash('该分类下还有软件，无法删除', 'error')
        return redirect(url_for('admin_categories'))
    db.session.delete(cat)
    db.session.commit()
    flash('分类已删除', 'success')
    return redirect(url_for('admin_categories'))


# --- User Admin ---
@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def admin_users():
    if request.method == 'POST':
        username = request.form.get('username')
        display_name = request.form.get('display_name')
        password = request.form.get('password')
        department_id = request.form.get('department_id', type=int)
        is_admin = request.form.get('is_admin') == 'on'

        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'error')
            return redirect(url_for('admin_users'))

        user = User(username=username, display_name=display_name,
                    department_id=department_id, is_admin=is_admin)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('用户已添加', 'success')
        return redirect(url_for('admin_users'))

    users = User.query.order_by(User.created_at.desc()).all()
    departments = Department.query.order_by(Department.name).all()
    return render_template('admin/users.html', users=users, departments=departments)


@app.route('/admin/users/edit/<int:id>', methods=['POST'])
@admin_required
def admin_users_edit(id):
    user = db.session.get(User, id)
    if not user:
        abort(404)
    user.display_name = request.form.get('display_name', user.display_name)
    user.department_id = request.form.get('department_id', type=int) or user.department_id
    user.is_admin = request.form.get('is_admin') == 'on'
    user.is_active = request.form.get('is_active') == 'on'
    new_pwd = request.form.get('password')
    if new_pwd:
        user.set_password(new_pwd)
    db.session.commit()
    flash('用户已更新', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/delete/<int:id>', methods=['POST'])
@admin_required
def admin_users_delete(id):
    if id == current_user.id:
        flash('不能删除当前登录的管理员', 'error')
        return redirect(url_for('admin_users'))
    user = db.session.get(User, id)
    if not user:
        abort(404)
    db.session.delete(user)
    db.session.commit()
    flash('用户已删除', 'success')
    return redirect(url_for('admin_users'))


# --- Department Admin ---
@app.route('/admin/departments', methods=['GET', 'POST'])
@admin_required
def admin_departments():
    if request.method == 'POST':
        name = request.form.get('name')
        if Department.query.filter_by(name=name).first():
            flash('部门已存在', 'error')
        else:
            dept = Department(name=name)
            db.session.add(dept)
            db.session.commit()
            flash('部门已添加', 'success')
        return redirect(url_for('admin_departments'))
    departments = Department.query.order_by(Department.name).all()
    return render_template('admin/departments.html', departments=departments)


@app.route('/admin/departments/edit/<int:id>', methods=['POST'])
@admin_required
def admin_departments_edit(id):
    dept = db.session.get(Department, id)
    if not dept:
        abort(404)
    dept.name = request.form.get('name', dept.name)
    db.session.commit()
    flash('部门已更新', 'success')
    return redirect(url_for('admin_departments'))


@app.route('/admin/departments/delete/<int:id>', methods=['POST'])
@admin_required
def admin_departments_delete(id):
    dept = db.session.get(Department, id)
    if not dept:
        abort(404)
    if dept.users.count() > 0:
        flash('该部门下还有用户，无法删除', 'error')
        return redirect(url_for('admin_departments'))
    db.session.delete(dept)
    db.session.commit()
    flash('部门已删除', 'success')
    return redirect(url_for('admin_departments'))


# --- Permission Admin ---
@app.route('/admin/permissions', methods=['GET', 'POST'])
@admin_required
def admin_permissions():
    if request.method == 'POST':
        department_id = request.form.get('department_id', type=int)
        # Clear existing permissions for this department
        Permission.query.filter_by(department_id=department_id).delete()
        category_ids = request.form.getlist('category_ids', type=int)
        for cid in category_ids:
            perm = Permission(department_id=department_id, category_id=cid)
            db.session.add(perm)
        db.session.commit()
        flash('权限已更新', 'success')
        return redirect(url_for('admin_permissions'))

    departments = Department.query.order_by(Department.name).all()
    categories = Category.query.order_by(Category.sort_order).all()
    # Build permission map: dept_id -> set of category_ids
    perm_map = {}
    for dept in departments:
        perms = Permission.query.filter_by(department_id=dept.id).all()
        perm_map[dept.id] = set(p.category_id for p in perms)
    return render_template('admin/permissions.html',
                           departments=departments,
                           categories=categories,
                           perm_map=perm_map)


# ─── Icon Route ────────────────────────────────────────────
@app.route('/icons/<path:filename>')
def serve_icon(filename):
    response = send_from_directory(app.config['ICON_FOLDER'], filename)
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


# ─── After Request (Caching) ──────────────────────────────
@app.after_request
def set_cache_headers(response):
    """为静态资源添加浏览器缓存头，减少重复请求"""
    if '/static/' in request.path or '/uploads/' in request.path:
        response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


# ─── Error Handlers ────────────────────────────────────────
@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


# ─── Orphan Cleanup ───────────────────────────────────────
def cleanup_orphan_files():
    """启动时清理磁盘上不在数据库中的孤立文件，释放空间"""
    upload_dir = app.config['UPLOAD_FOLDER']
    icon_dir = app.config['ICON_FOLDER']

    # 收集数据库中所有有效的文件名
    db_files = set()
    db_icons = set()
    for sw in Software.query.all():
        if sw.filename:
            db_files.add(sw.filename)
        if sw.icon:
            db_icons.add(sw.icon)

    # 清理 uploads 目录中的孤立软件包
    removed_files = 0
    freed_bytes = 0
    if os.path.isdir(upload_dir):
        for fname in os.listdir(upload_dir):
            fpath = os.path.join(upload_dir, fname)
            if os.path.isfile(fpath) and fname not in db_files:
                freed_bytes += os.path.getsize(fpath)
                os.remove(fpath)
                removed_files += 1

    # 清理 icons 目录中的孤立图标
    removed_icons = 0
    if os.path.isdir(icon_dir):
        for fname in os.listdir(icon_dir):
            fpath = os.path.join(icon_dir, fname)
            if os.path.isfile(fpath) and fname not in db_icons:
                os.remove(fpath)
                removed_icons += 1

    if removed_files or removed_icons:
        freed_mb = freed_bytes / 1024 / 1024
        print(f'[Cleanup] 删除 {removed_files} 个孤立软件包, {removed_icons} 个孤立图标, 释放 {freed_mb:.1f} MB')


# ─── Run ───────────────────────────────────────────────────
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        cleanup_orphan_files()
    app.run(host='0.0.0.0', port=5000, debug=False)
