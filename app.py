from flask import (
    Flask, render_template, request, redirect,
    url_for, abort, session, flash, jsonify, Response
)
from werkzeug.utils import secure_filename
# pip install Werkzeug if missing
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import json, os, functools, re, time, shutil

# -----------------------------------------------------------------------------
# Flask setup
# -----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("MUNIVERSE_SECRET", "dev-change-me")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB uploads

# Site URL for sitemaps / SEO
SITE_URL = os.environ.get("MUNIVERSE_SITE_URL", "https://www.muniverse.social")

# Admin portal password (set in env for production)
ADMIN_PORTAL_PASSWORD = os.environ.get(
    "MUNIVERSE_ADMIN_PASSWORD",
    "kwQUkoOb45A2O6qAWXqmzjP8Tn7FrkrH"
)

# -----------------------------------------------------------------------------
# Data paths
# -----------------------------------------------------------------------------
DATA_DIR        = "data"
USERS_FILE      = os.path.join(DATA_DIR, "users.json")
POSTS_FILE      = os.path.join(DATA_DIR, "posts.json")
CONF_FILE       = os.path.join(DATA_DIR, "conferences.json")
FORUM_THREADS   = os.path.join(DATA_DIR, "forum_threads.json")
FORUM_REPLIES   = os.path.join(DATA_DIR, "forum_replies.json")

# New: pending conferences + admin notifications
CONF_PENDING_FILE = os.path.join(DATA_DIR, "pending_conferences.json")
NOTIFS_FILE       = os.path.join(DATA_DIR, "admin_notifications.json")

os.makedirs(DATA_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# Upload dirs (absolute under /static)
# -----------------------------------------------------------------------------
POST_UPLOAD_DIR = os.path.join(app.static_folder, "img", "posts")
USER_UPLOAD_DIR = os.path.join(app.static_folder, "img", "users")
CONF_UPLOAD_DIR = os.path.join(app.static_folder, "img", "conferences")
# New: where pending conference banners are staged before approval
PENDING_UPLOAD_DIR = os.path.join(CONF_UPLOAD_DIR, "pending")

for d in (POST_UPLOAD_DIR, USER_UPLOAD_DIR, CONF_UPLOAD_DIR, PENDING_UPLOAD_DIR):
    os.makedirs(d, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# -----------------------------------------------------------------------------
# General Helpers
# -----------------------------------------------------------------------------
def delete_static_file(path_suffix: str):
    """Safely delete a file from the static folder, avoiding defaults."""
    if not path_suffix or "default.png" in path_suffix:
        return
    try:
        abs_path = os.path.join(app.static_folder, path_suffix)
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception as e:
        app.logger.error(f"Error deleting file {path_suffix}: {e}")


def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s[:80] or "topic"


def add_notification(kind: str, payload: dict):
    notifs = load_json(NOTIFS_FILE)
    nid = (max([n.get("id", 0) for n in notifs], default=0) + 1) if notifs else 1
    notifs.append({"id": nid, "kind": kind, "payload": payload, "ts": int(time.time())})
    save_json(NOTIFS_FILE, notifs)

# -----------------------------------------------------------------------------
# JSON helpers
# -----------------------------------------------------------------------------
def load_json(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def next_id(items):
    """Robustly gets the next integer ID from a list of dicts."""
    if not items:
        return 1
    max_id = 0
    for item in items:
        try:
            item_id = int(item.get("id", 0))
            if item_id > max_id:
                max_id = item_id
        except (ValueError, TypeError):
            continue
    return max_id + 1

# --- users helpers ---
def find_user(users, username):
    return next((u for u in users if u.get("username") == username), None)


def save_user(users, user):
    for i, u in enumerate(users):
        if u.get("username") == user["username"]:
            users[i] = user
            break
    else:
        users.append(user)
    save_json(USERS_FILE, users)

# --- posts helpers ---
def normalize_post(post: dict) -> dict:
    post.setdefault("likes", 0)
    post.setdefault("liked_by", [])
    post.setdefault("comments", [])
    return post


def get_post_by_id(post_id: int):
    posts = load_json(POSTS_FILE)
    for p in posts:
        if p.get("id") == post_id:
            return posts, p
    return posts, None


def save_posts(posts):
    save_json(POSTS_FILE, posts)

# -----------------------------------------------------------------------------
# Auth helpers
# -----------------------------------------------------------------------------
def get_current_user():
    uname = session.get("username")
    if not uname:
        return None
    users = load_json(USERS_FILE)
    return find_user(users, uname)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            flash("Please sign in to continue.", "warn")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        me = get_current_user()
        if not me or me.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("feed"))
        return view(*args, **kwargs)
    return wrapped


def is_admin_verified() -> bool:
    u = get_current_user()
    return bool(u and u.get("role") == "admin" and session.get("admin_verified") is True)


@app.context_processor
def inject_user():
    return {"current_user": get_current_user()}

# -----------------------------------------------------------------------------
# Insights helper for Admin
# -----------------------------------------------------------------------------
def build_insights(users, posts, limit=10):
    by_user = {
        u["username"]: {
            "likes": 0,
            "posts": 0,
            "profile_pic": u.get("profile_pic", "img/users/default.png"),
            "followers": u.get("followers", []),
            "following": u.get("following", [])
        }
        for u in users
        if u.get("username")
    }

    total_likes = 0
    total_comments = 0
    for p in posts:
        p = normalize_post(p)
        likes = int(p.get("likes", 0))
        total_likes += likes
        total_comments += len(p.get("comments", []))
        uname = p.get("username")
        if uname in by_user:
            by_user[uname]["likes"] += likes
            by_user[uname]["posts"] += 1

    top_users = []
    for u in users:
        uname = u.get("username")
        if not uname:
            continue
        stats = by_user.get(uname, {
            "likes": 0,
            "posts": 0,
            "profile_pic": u.get("profile_pic", "img/users/default.png"),
            "followers": u.get("followers", []),
            "following": u.get("following", [])
        })
        top_users.append({
            "username": uname,
            "profile_pic": stats["profile_pic"],
            "likes": stats["likes"],
            "posts": stats["posts"],
            "followers": u.get("followers", []),
            "following": u.get("following", [])
        })
    top_users.sort(key=lambda x: x["likes"], reverse=True)
    top_users = top_users[:limit]

    top_posts = sorted(
        [normalize_post(p) for p in posts],
        key=lambda x: x.get("likes", 0),
        reverse=True
    )[:limit]

    stats = {
        "total_users": len(users),
        "total_posts": len(posts),
        "total_likes": total_likes,
        "total_comments": total_comments,
    }
    return stats, {"top_users_by_likes": top_users, "top_posts": top_posts}

# -----------------------------------------------------------------------------
# Global headers (SEO-ish caching + security)
# -----------------------------------------------------------------------------
@app.after_request
def add_global_headers(response):
    # basic caching: strong cache for static, light cache for dynamic
    if request.path.startswith("/static/"):
        response.headers.setdefault(
            "Cache-Control",
            "public, max-age=31536000, immutable"
        )
    else:
        response.headers.setdefault(
            "Cache-Control",
            "public, max-age=60"
        )

    # some simple security headers
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault(
        "Strict-Transport-Security",
        "max-age=31536000; includeSubDomains"
    )
    return response

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def onboarding():
    return render_template("onboarding.html")

# -------------------- Auth --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        users = load_json(USERS_FILE)
        user = find_user(users, username)
        if not user or not user.get("password_hash") or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))
        session["username"] = username
        # Reset admin verification on login (safer)
        session["admin_verified"] = False
        nxt = request.args.get("next") or url_for("feed")
        return redirect(nxt)
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("onboarding"))


@app.route("/robots.txt")
def robots():
    # serve static robots.txt
    return app.send_static_file("robots.txt")

# -------------------- SITEMAPS --------------------
@app.route("/sitemap.xml")
def sitemap_index():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>{SITE_URL}/sitemap-static.xml</loc></sitemap>
  <sitemap><loc>{SITE_URL}/sitemap-posts.xml</loc></sitemap>
  <sitemap><loc>{SITE_URL}/sitemap-profiles.xml</loc></sitemap>
  <sitemap><loc>{SITE_URL}/sitemap-conferences.xml</loc></sitemap>
  <sitemap><loc>{SITE_URL}/sitemap-forums.xml</loc></sitemap>
</sitemapindex>"""
    return Response(xml, mimetype="application/xml")


@app.route("/sitemap-static.xml")
def sitemap_static():
    pages = [
        ("/", "weekly", "0.9"),
        ("/feed", "hourly", "0.9"),
        ("/explore", "hourly", "0.9"),
        ("/forums", "daily", "0.8"),
        ("/conferences", "daily", "0.8"),
        ("/about", "monthly", "0.5"),
        ("/privacypolicy", "yearly", "0.3"),
        ("/login", "weekly", "0.4"),
        ("/signup", "weekly", "0.4"),
    ]
    urls_xml = []
    today = datetime.utcnow().date().isoformat()
    for path, freq, prio in pages:
        urls_xml.append(f"""
  <url>
    <loc>{SITE_URL}{path}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{prio}</priority>
  </url>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls_xml)}
</urlset>"""
    return Response(xml, mimetype="application/xml")


@app.route("/sitemap-posts.xml")
def sitemap_posts():
    posts = load_json(POSTS_FILE)
    urls_xml = []
    today = datetime.utcnow().date().isoformat()
    for p in posts:
        pid = p.get("id")
        if not pid:
            continue
        loc = f"{SITE_URL}/post/{pid}"
        lastmod = today
        urls_xml.append(f"""
  <url>
    <loc>{loc}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls_xml)}
</urlset>"""
    return Response(xml, mimetype="application/xml")


@app.route("/sitemap-profiles.xml")
def sitemap_profiles():
    users = load_json(USERS_FILE)
    urls_xml = []
    today = datetime.utcnow().date().isoformat()
    for u in users:
        uname = u.get("username")
        if not uname:
            continue
        loc = f"{SITE_URL}/profile/{uname}"
        urls_xml.append(f"""
  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls_xml)}
</urlset>"""
    return Response(xml, mimetype="application/xml")


@app.route("/sitemap-conferences.xml")
def sitemap_conferences():
    confs = load_json(CONF_FILE)
    urls_xml = []
    for c in confs:
        cid = c.get("id")
        if not cid:
            continue
        loc = f"{SITE_URL}/conference/{cid}"
        lastmod = c.get("date") or datetime.utcnow().date().isoformat()
        urls_xml.append(f"""
  <url>
    <loc>{loc}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.85</priority>
  </url>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls_xml)}
</urlset>"""
    return Response(xml, mimetype="application/xml")


@app.route("/sitemap-forums.xml")
def sitemap_forums():
    threads = load_json(FORUM_THREADS)
    urls_xml = []
    for t in threads:
        slug = t.get("slug") or str(t.get("id"))
        loc = f"{SITE_URL}/forums/{slug}"
        ts = t.get("created_ts", int(time.time()))
        lastmod = datetime.utcfromtimestamp(ts).date().isoformat()
        urls_xml.append(f"""
  <url>
    <loc>{loc}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls_xml)}
</urlset>"""
    return Response(xml, mimetype="application/xml")

# -------------------- Signup --------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users = load_json(USERS_FILE)
        username = (request.form.get("username") or "").strip()
        if not username:
            flash("Username is required.", "error")
            return redirect(url_for("signup"))
        if find_user(users, username):
            flash("Username already taken.", "error")
            return redirect(url_for("signup"))

        name   = (request.form.get("name") or "").strip()
        school = (request.form.get("school") or "").strip()
        bio    = (request.form.get("bio") or "").strip()
        pw     = (request.form.get("password") or "").strip()
        pw2    = (request.form.get("password_confirm") or "").strip()
        if not pw or pw != pw2:
            flash("Passwords do not match.", "error")
            return redirect(url_for("signup"))

        photo_path = "img/users/default.png"
        file = request.files.get("profile_photo")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid profile photo type.", "error")
                return redirect(url_for("signup"))
            filename = secure_filename(file.filename)
            ext = filename.rsplit(".", 1)[1].lower()
            final_name = f"{username}.{ext}"
            file.save(os.path.join(USER_UPLOAD_DIR, final_name))
            photo_path = f"img/users/{final_name}"

        new_user = {
            "name": name,
            "username": username,
            "school": school,
            "bio": bio,
            "profile_pic": photo_path,
            "password_hash": generate_password_hash(pw),
            "attendingConferences": [],
            "followers": [],
            "following": []
        }
        users.append(new_user)
        save_json(USERS_FILE, users)

        session["username"] = username
        session["admin_verified"] = False
        return redirect(url_for("feed"))
    return render_template("signup.html")

# -------------------- Settings: Password & Profile --------------------
@app.route("/settings/password", methods=["GET", "POST"])
@login_required
def settings_password():
    users = load_json(USERS_FILE)
    me = find_user(users, session["username"])
    if not me:
        session.clear()
        abort(403)

    if request.method == "POST":
        old = (request.form.get("old_password") or "").strip()
        new = (request.form.get("new_password") or "").strip()
        conf = (request.form.get("confirm_password") or "").strip()
        if not me.get("password_hash") or not check_password_hash(me["password_hash"], old):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("settings_password"))
        if not new or new != conf:
            flash("New passwords do not match.", "error")
            return redirect(url_for("settings_password"))
        me["password_hash"] = generate_password_hash(new)
        save_user(users, me)
        flash("Password updated.", "ok")
        return redirect(url_for("profile", username=me["username"]))
    return render_template("settings_password.html", user=me)


@app.route("/settings/profile", methods=["GET", "POST"])
@login_required
def settings_profile():
    users = load_json(USERS_FILE)
    me = find_user(users, session["username"])
    if not me:
        session.clear()
        abort(403)

    if request.method == "POST":
        me["name"] = (request.form.get("name") or "").strip()
        me["school"] = (request.form.get("school") or "").strip()
        me["bio"] = (request.form.get("bio") or "").strip()

        file = request.files.get("profile_photo")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid profile photo type.", "error")
                return redirect(url_for("settings_profile"))

            old_pic_path = me.get("profile_pic")
            filename = secure_filename(file.filename)
            ext = filename.rsplit(".", 1)[1].lower()
            final_name = f"{me['username']}.{ext}"
            save_path = os.path.join(USER_UPLOAD_DIR, final_name)
            file.save(save_path)
            me["profile_pic"] = f"img/users/{final_name}"
            delete_static_file(old_pic_path)

        save_user(users, me)
        flash("Profile updated.", "ok")
        return redirect(url_for("profile", username=me["username"]))

    return render_template("settings_profile.html", user=me)

# -------------------- Explore / Feed / Post pages --------------------
@app.route("/explore")
def explore():
    posts = load_json(POSTS_FILE)
    q = (request.args.get("q") or "").strip().lower()
    if q:
        def hit(p):
            cap = (p.get("caption") or "").lower()
            user = (p.get("username") or "").lower()
            return q in cap or q in user
        posts = [p for p in posts if hit(p)]
    posts = [normalize_post(p) for p in posts]
    posts.sort(key=lambda x: x.get("id", 0), reverse=True)
    return render_template("explore.html", posts=posts, q=q)


@app.route("/feed")
def feed():
    posts = load_json(POSTS_FILE)
    posts = [normalize_post(p) for p in posts]
    posts.sort(key=lambda x: x.get("id", 0), reverse=True)
    return render_template("feed.html", posts=posts)


@app.route("/post/<int:post_id>")
def post(post_id):
    posts = load_json(POSTS_FILE)
    item = next((p for p in posts if p.get("id") == post_id), None)
    if not item:
        abort(404, "Post not found")
    normalize_post(item)
    return render_template("post.html", post=item)

# Edit & Delete Post
@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def post_edit(post_id):
    posts = load_json(POSTS_FILE)
    post = next((p for p in posts if p.get("id") == post_id), None)
    if not post:
        abort(404, "Post not found")

    if post.get("username") != session["username"]:
        abort(403)

    if request.method == "POST":
        post["caption"] = (request.form.get("caption") or "").strip()

        file = request.files.get("image_file")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image type.", "error")
                return redirect(url_for("post_edit", post_id=post_id))

            old_image_path = post.get("image")
            filename = secure_filename(file.filename)
            file.save(os.path.join(POST_UPLOAD_DIR, filename))
            post["image"] = f"img/posts/{filename}"
            delete_static_file(old_image_path)

        save_json(POSTS_FILE, posts)
        flash("Post updated.", "ok")
        return redirect(url_for("profile", username=session["username"]))

    return render_template("post_edit.html", post=post)


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def post_delete(post_id):
    posts = load_json(POSTS_FILE)
    idx = next((i for i, p in enumerate(posts) if p.get("id") == post_id), None)
    if idx is None:
        abort(404, "Post not found")

    post_to_delete = posts[idx]
    if post_to_delete.get("username") != session["username"]:
        abort(403)

    delete_static_file(post_to_delete.get("image"))
    posts.pop(idx)
    save_json(POSTS_FILE, posts)
    flash("Post deleted.", "ok")
    return redirect(url_for("profile", username=session["username"]))

# -------------------- Add Post --------------------
@app.route("/addpost", methods=["GET", "POST"])
@login_required
def addpost():
    if request.method == "POST":
        user = get_current_user()
        posts = load_json(POSTS_FILE)

        caption = (request.form.get("caption") or "").strip()
        file = request.files.get("image_file")
        if not file or not file.filename:
            flash("An image file is required.", "error")
            return redirect(url_for("addpost"))
        if not allowed_file(file.filename):
            flash("Invalid image type. Allowed: png, jpg, jpeg, gif, webp.", "error")
            return redirect(url_for("addpost"))

        filename = secure_filename(file.filename)
        file.save(os.path.join(POST_UPLOAD_DIR, filename))
        image_path = f"img/posts/{filename}"

        new_post = {
            "id": next_id(posts),
            "username": user["username"],
            "caption": caption,
            "image": image_path,
            "likes": 0,
            "liked_by": [],
            "comments": []
        }
        posts.append(new_post)
        save_json(POSTS_FILE, posts)
        return redirect(url_for("feed"))

    return render_template("addpost.html")

# -------------------- Likes & Comments APIs --------------------
@app.route("/post/<int:post_id>/like", methods=["POST"])
@login_required
def like_post(post_id):
    user = get_current_user()
    posts, post = get_post_by_id(post_id)
    if not post:
        return jsonify({"ok": False, "error": "post_not_found"}), 404

    post = normalize_post(post)
    u = user["username"]
    if u in post["liked_by"]:
        post["liked_by"].remove(u)
    else:
        post["liked_by"].append(u)
    post["likes"] = len(post["liked_by"])
    save_posts(posts)
    return jsonify({"ok": True, "liked": (u in post["liked_by"]), "likes": post["likes"]})


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def comment_post(post_id):
    user = get_current_user()
    text = (request.form.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400
    if len(text) > 1000:
        return jsonify({"ok": False, "error": "too_long"}), 400

    posts, post = get_post_by_id(post_id)
    if not post:
        return jsonify({"ok": False, "error": "post_not_found"}), 404

    post = normalize_post(post)
    new_id = next_id(post["comments"])
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    comment_data = {
        "id": new_id,
        "username": user["username"],
        "text": text,
        "ts": ts
    }
    post["comments"].append(comment_data)
    save_posts(posts)
    return jsonify({"ok": True, "comment": comment_data, "count": len(post["comments"])})

# -------------------- Conferences --------------------
@app.route("/conferences")
def conferences():
    confs = load_json(CONF_FILE)
    return render_template("conferences.html", conferences=confs)


@app.route("/conference/<int:conf_id>")
def conference(conf_id):
    confs = load_json(CONF_FILE)
    conf = next((c for c in confs if c.get("id") == conf_id), None)
    if not conf:
        abort(404, "Conference not found")
    return render_template("conference.html", conference=conf)

# Submit-for-approval flow (stores to pending list + pending banner folder)
@app.route("/addconference", methods=["GET", "POST"])
@login_required
def addconference():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        date = (request.form.get("date") or "").strip()
        location = (request.form.get("location") or "").strip()
        slug_id = (request.form.get("id") or "").strip()
        description = (request.form.get("description") or "").strip()
        tags_raw = (request.form.get("tags") or "").strip()

        if not all([slug_id, name, date, location, description]):
            flash("Please fill all required fields (ID, name, date, location, description).", "error")
            return redirect(url_for("addconference"))

        file = request.files.get("banner_file")
        if not file or not file.filename:
            flash("A banner image is required.", "error")
            return redirect(url_for("addconference"))
        if not allowed_file(file.filename):
            flash("Invalid banner type. Allowed: png, jpg, jpeg, gif, webp.", "error")
            return redirect(url_for("addconference"))

        filename = secure_filename(file.filename)
        filename = f"{int(time.time())}_{filename}"
        file.save(os.path.join(PENDING_UPLOAD_DIR, filename))
        pending_banner_path = f"img/conferences/pending/{filename}"

        pendings = load_json(CONF_PENDING_FILE)
        pending_item = {
            "id": next_id(pendings),
            "slug": slug_id,
            "name": name,
            "date": date,
            "location": location,
            "description": description,
            "banner": pending_banner_path,
            "tags": [t.strip() for t in tags_raw.split(",") if t.strip()],
            "submitted_by": session.get("username"),
            "submitted_ts": int(time.time()),
            "status": "pending"
        }
        pendings.append(pending_item)
        save_json(CONF_PENDING_FILE, pendings)

        add_notification("conference_submission", {
            "pending_id": pending_item["id"],
            "slug": slug_id,
            "name": name,
            "submitted_by": pending_item["submitted_by"]
        })

        flash("Conference submitted for admin approval. It will appear after approval.", "ok")
        return redirect(url_for("conferences"))

    return render_template("addconference.html")

# -------------------- Follow system --------------------
@app.route("/follow/<username>", methods=["POST"])
@login_required
def follow(username):
    me_name = session["username"]
    if me_name == username:
        return jsonify({"ok": False, "error": "cannot_follow_self"}), 400

    users = load_json(USERS_FILE)
    me = find_user(users, me_name)
    other = find_user(users, username)
    if not other:
        return jsonify({"ok": False, "error": "user_not_found"}), 404

    me.setdefault("following", [])
    other.setdefault("followers", [])

    if username in me["following"]:
        me["following"].remove(username)
        if me_name in other["followers"]:
            other["followers"].remove(me_name)
        action = "unfollowed"
    else:
        me["following"].append(username)
        if me_name not in other["followers"]:
            other["followers"].append(me_name)
        action = "followed"

    save_user(users, me)
    save_user(users, other)

    return jsonify({
        "ok": True,
        "action": action,
        "followers": len(other.get("followers", [])),
        "following": len(me.get("following", []))
    })

# -------------------- Profiles --------------------
@app.route("/profile/<username>")
def profile(username):
    users = load_json(USERS_FILE)
    user = find_user(users, username)
    if not user:
        abort(404, "User not found")
    posts = load_json(POSTS_FILE)

    user.setdefault("followers", [])
    user.setdefault("following", [])
    user_posts = [normalize_post(p) for p in posts if p.get("username") == username]
    user_posts.sort(key=lambda p: p.get("id", 0), reverse=True)
    return render_template("profile.html", user=user, posts=user_posts)

# -------------------- Forums --------------------
@app.route("/forums")
def forums():
    threads = load_json(FORUM_THREADS)
    q = (request.args.get("q") or "").strip().lower()
    tag = (request.args.get("tag") or "").strip().lower()

    filtered_threads = threads
    if q:
        def hit(t):
            content = " ".join([
                t.get("title", ""),
                t.get("body", ""),
                " ".join(t.get("tags", []))
            ]).lower()
            return q in content
        filtered_threads = [t for t in filtered_threads if hit(t)]
    if tag:
        filtered_threads = [
            t for t in filtered_threads
            if tag in [x.lower() for x in t.get("tags", [])]
        ]

    filtered_threads.sort(key=lambda t: t.get("created_ts", 0), reverse=True)
    return render_template("forums.html", threads=filtered_threads, q=q, tag=tag)


@app.route("/forums/new", methods=["GET", "POST"])
@login_required
def forum_new():
    if request.method == "POST":
        me = get_current_user()
        title = (request.form.get("title") or "").strip()
        body  = (request.form.get("body") or "").strip()
        tags_raw = (request.form.get("tags") or "").strip()

        if not title or not body:
            flash("Title and body are required.", "error")
            return redirect(url_for("forum_new"))

        threads = load_json(FORUM_THREADS)
        tid = next_id(threads)
        slug = f"{slugify(title)}-{tid}"
        thread = {
            "id": tid,
            "slug": slug,
            "title": title,
            "body": body,
            "tags": [t.strip() for t in tags_raw.split(",") if t.strip()],
            "author": me["username"],
            "created_ts": int(time.time()),
            "replies": 0,
            "views": 0
        }
        threads.append(thread)
        save_json(FORUM_THREADS, threads)
        flash("Thread created.", "ok")
        return redirect(url_for("forum_thread", slug=slug))
    return render_template("forum_new.html")


@app.route("/forums/<slug>", methods=["GET", "POST"])
def forum_thread(slug):
    threads = load_json(FORUM_THREADS)
    thread_idx = next(
        (i for i, t in enumerate(threads)
         if t.get("slug") == slug or str(t.get("id")) == slug),
        None
    )
    if thread_idx is None:
        abort(404, "Thread not found")
    thread = threads[thread_idx]

    # Increment views and save immediately
    thread["views"] = int(thread.get("views", 0)) + 1
    save_json(FORUM_THREADS, threads)

    if request.method == "POST":
        if not session.get("username"):
            flash("Sign in to reply.", "warn")
            return redirect(url_for("login", next=request.path))

        me = get_current_user()
        text = (request.form.get("text") or "").strip()
        if not text:
            flash("Reply cannot be empty.", "error")
            return redirect(url_for("forum_thread", slug=slug))

        replies = load_json(FORUM_REPLIES)
        reply = {
            "id": next_id(replies),
            "thread_id": thread["id"],
            "author": me["username"],
            "text": text,
            "created_ts": int(time.time())
        }
        replies.append(reply)
        save_json(FORUM_REPLIES, replies)

        thread["replies"] = int(thread.get("replies", 0)) + 1
        save_json(FORUM_THREADS, threads)

        flash("Reply posted.", "ok")
        return redirect(url_for("forum_thread", slug=slug))

    all_replies = load_json(FORUM_REPLIES)
    thread_replies = [r for r in all_replies if r.get("thread_id") == thread["id"]]
    thread_replies.sort(key=lambda r: r.get("created_ts", 0))
    return render_template("forum_thread.html", thread=thread, replies=thread_replies)

# -------------------- Static Pages --------------------
@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/privacypolicy")
def privacypolicy():
    return render_template("privacypolicy.html")

# -------------------- Admin Gate + Portal + Actions --------------------
@app.route("/admin/verify", methods=["POST"])
@login_required
@admin_required
def admin_verify():
    pw = (request.form.get("admin_password") or "").strip()
    if pw and pw == ADMIN_PORTAL_PASSWORD:
        session["admin_verified"] = True
        flash("Admin mode enabled.", "ok")
    else:
        session["admin_verified"] = False
        flash("Invalid admin password.", "error")
    return redirect(url_for("admin_portal"))


@app.route("/admin")
@login_required
@admin_required
def admin_portal():
    verified = is_admin_verified()

    uq = (request.args.get("uq") or "").strip().lower()
    users = load_json(USERS_FILE)
    posts = [normalize_post(p) for p in load_json(POSTS_FILE)]

    stats, insights = build_insights(users, posts, limit=10)

    # attach simple stats to users for table
    by_user = {u["username"]: {"likes": 0, "posts": 0} for u in users if u.get("username")}
    for p in posts:
        uname = p.get("username")
        if uname in by_user:
            by_user[uname]["likes"] += int(p.get("likes", 0))
            by_user[uname]["posts"] += 1
    for u in users:
        uname = u.get("username")
        if not uname:
            continue
        u["stats"] = by_user.get(uname, {"likes": 0, "posts": 0})

    # filter users if query
    if uq:
        def hit(u):
            src = f"{u.get('username','').lower()} {u.get('name','').lower()}"
            return uq in src
        users = [u for u in users if hit(u)]

    posts = sorted(posts, key=lambda x: x.get("id", 0), reverse=True)

    pendings = []
    if verified:
        pendings = sorted(
            load_json(CONF_PENDING_FILE),
            key=lambda x: x.get("submitted_ts", 0),
            reverse=True
        )

    return render_template(
        "adminportal.html",
        verified=verified,
        users=users, posts=posts,
        stats=stats, insights=insights, uq=uq,
        pendings=pendings
    )


@app.route("/admin/delete_post", methods=["POST"])
@login_required
@admin_required
def admin_delete_post():
    if not is_admin_verified():
        abort(403)
    try:
        pid = int(request.form.get("post_id"))
    except Exception:
        flash("Invalid post id.", "error")
        return redirect(url_for("admin_portal"))

    posts = load_json(POSTS_FILE)
    target = next((p for p in posts if p.get("id") == pid), None)
    if not target:
        flash(f"Post #{pid} not found.", "warn")
        return redirect(url_for("admin_portal"))

    delete_static_file(target.get("image"))
    posts = [p for p in posts if p.get("id") != pid]
    save_json(POSTS_FILE, posts)
    flash(f"Deleted post #{pid}.", "ok")
    return redirect(url_for("admin_portal"))


@app.route("/admin/delete_user", methods=["POST"])
@login_required
@admin_required
def admin_delete_user():
    if not is_admin_verified():
        abort(403)
    uname = (request.form.get("username") or "").strip()
    if not uname:
        flash("Missing username.", "error")
        return redirect(url_for("admin_portal"))

    users = load_json(USERS_FILE)
    posts = load_json(POSTS_FILE)

    user = find_user(users, uname)
    if not user:
        flash(f"User @{uname} not found.", "warn")
        return redirect(url_for("admin_portal"))

    # Remove user's uploaded avatar (if not default)
    delete_static_file(user.get("profile_pic"))

    # Remove user's posts & images
    deleted = 0
    for p in list(posts):
        if p.get("username") == uname:
            delete_static_file(p.get("image"))
            posts.remove(p)
            deleted += 1
    save_json(POSTS_FILE, posts)

    # Remove user & cleanup follow relationships
    users = [u for u in users if u.get("username") != uname]
    for u in users:
        u["followers"] = [x for x in u.get("followers", []) if x != uname]
        u["following"] = [x for x in u.get("following", []) if x != uname]
    save_json(USERS_FILE, users)

    flash(f"Deleted user @{uname} and {deleted} posts.", "ok")
    return redirect(url_for("admin_portal"))


@app.route("/admin/toggle_admin", methods=["POST"])
@login_required
@admin_required
def admin_toggle_admin():
    if not is_admin_verified():
        abort(403)
    uname = (request.form.get("username") or "").strip()
    if not uname:
        flash("Missing username.", "error")
        return redirect(url_for("admin_portal"))

    users = load_json(USERS_FILE)
    user = find_user(users, uname)
    if not user:
        flash("User not found.", "warn")
        return redirect(url_for("admin_portal"))

    user["role"] = "admin" if user.get("role") != "admin" else "user"
    save_user(users, user)
    flash(f"@{uname} role is now: {user['role']}.", "ok")
    return redirect(url_for("admin_portal"))

# ---- Approve / Reject conference submissions (admin verified only) ----
@app.route("/admin/conf/approve", methods=["POST"])
@login_required
@admin_required
def admin_conf_approve():
    if not is_admin_verified():
        abort(403)
    pid = int(request.form.get("pending_id", 0))
    pendings = load_json(CONF_PENDING_FILE)
    idx = next((i for i, p in enumerate(pendings) if int(p.get("id", 0)) == pid), None)
    if idx is None:
        flash("Pending item not found.", "error")
        return redirect(url_for("admin_portal"))

    item = pendings[idx]
    # move banner from pending to live folder
    src_rel = item["banner"]  # "img/conferences/pending/xxx"
    src_abs = os.path.join(app.static_folder, src_rel)
    live_dir = os.path.join(app.static_folder, "img", "conferences")
    os.makedirs(live_dir, exist_ok=True)
    final_name = f"{int(time.time())}_{os.path.basename(src_abs)}"
    dst_abs = os.path.join(live_dir, final_name)
    shutil.move(src_abs, dst_abs)
    item["banner"] = f"img/conferences/{final_name}"

    # write to approved conferences
    confs = load_json(CONF_FILE)
    confs.append({
        "id": next_id(confs),
        "name": item["name"],
        "date": item["date"],
        "location": item["location"],
        "description": item["description"],
        "banner": item["banner"],
        "tags": item.get("tags", []),
    })
    save_json(CONF_FILE, confs)

    # remove pending
    pendings.pop(idx)
    save_json(CONF_PENDING_FILE, pendings)

    flash("Conference approved & published.", "ok")
    return redirect(url_for("admin_portal"))


@app.route("/admin/conf/reject", methods=["POST"])
@login_required
@admin_required
def admin_conf_reject():
    if not is_admin_verified():
        abort(403)
    pid = int(request.form.get("pending_id", 0))
    pendings = load_json(CONF_PENDING_FILE)
    idx = next((i for i, p in enumerate(pendings) if int(p.get("id", 0)) == pid), None)
    if idx is None:
        flash("Pending item not found.", "error")
        return redirect(url_for("admin_portal"))

    item = pendings[idx]
    # delete the pending banner file
    delete_static_file(item.get("banner"))
    pendings.pop(idx)
    save_json(CONF_PENDING_FILE, pendings)
    flash("Conference submission rejected.", "ok")
    return redirect(url_for("admin_portal"))

# -------------------- Debug uploads --------------------
@app.route("/_uploads")
def _uploads():
    info = {
        "static_folder": app.static_folder,
        "POST_UPLOAD_DIR": POST_UPLOAD_DIR,
        "USER_UPLOAD_DIR": USER_UPLOAD_DIR,
        "CONF_UPLOAD_DIR": CONF_UPLOAD_DIR,
        "post_files": [], "user_files": [], "conference_files": []
    }
    try:
        info["post_files"] = sorted(os.listdir(POST_UPLOAD_DIR))
    except Exception as e:
        info["post_files"] = [f"<error: {e}>"]
    try:
        info["user_files"] = sorted(os.listdir(USER_UPLOAD_DIR))
    except Exception as e:
        info["user_files"] = [f"<error: {e}>"]
    try:
        info["conference_files"] = sorted(os.listdir(CONF_UPLOAD_DIR))
    except Exception as e:
        info["conference_files"] = [f"<error: {e}>"]
    return info

# -------------------- 404 handler --------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("ROOT:", app.root_path)
    print("TEMPLATES:", os.path.join(app.root_path, app.template_folder))
    print("STATIC:", os.path.join(app.root_path, app.static_folder))
    app.run(debug=True)
