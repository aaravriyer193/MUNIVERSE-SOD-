from flask import (
    Flask, render_template, request, redirect,
    url_for, abort, session, flash, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import json, os, functools, re, time

# -----------------------------------------------------------------------------
# Flask setup
# -----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("MUNIVERSE_SECRET", "dev-change-me")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB uploads

# -----------------------------------------------------------------------------
# Data paths
# -----------------------------------------------------------------------------
DATA_DIR   = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
POSTS_FILE = os.path.join(DATA_DIR, "posts.json")
CONF_FILE  = os.path.join(DATA_DIR, "conferences.json")
FORUM_THREADS = os.path.join(DATA_DIR, "forum_threads.json")
FORUM_REPLIES = os.path.join(DATA_DIR, "forum_replies.json")
os.makedirs(DATA_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# Upload dirs (absolute under /static)
# -----------------------------------------------------------------------------
POST_UPLOAD_DIR = os.path.join(app.static_folder, "img", "posts")
USER_UPLOAD_DIR = os.path.join(app.static_folder, "img", "users")
CONF_UPLOAD_DIR = os.path.join(app.static_folder, "img", "conferences")
for d in (POST_UPLOAD_DIR, USER_UPLOAD_DIR, CONF_UPLOAD_DIR):
    os.makedirs(d, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# -----------------------------------------------------------------------------
# JSON helpers
# -----------------------------------------------------------------------------
def load_json(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

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

# --- forum helpers ---
def next_id(items):
    return (max((x.get("id", 0) for x in items), default=0) + 1) if items else 1

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s[:80] or "topic"

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

@app.context_processor
def inject_user():
    return {"current_user": get_current_user()}

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
        nxt = request.args.get("next") or url_for("feed")
        return redirect(nxt)
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("onboarding"))

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

        # OPTIONAL profile photo
        photo_path = (request.form.get("profile_pic") or "").strip()
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
        if not photo_path:
            photo_path = "img/users/default.png"  # ensure this exists in static/img/users

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
        return redirect(url_for("feed"))
    return render_template("signup.html")

# -------------------- Password settings --------------------
@app.route("/settings/password", methods=["GET", "POST"])
@login_required
def settings_password():
    users = load_json(USERS_FILE)
    me = get_current_user()
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
    posts = sorted(posts, key=lambda x: x.get("id", 0), reverse=True)
    return render_template("explore.html", posts=posts, q=q)

@app.route("/feed")
def feed():
    posts = load_json(POSTS_FILE)
    posts = [normalize_post(p) for p in posts]
    posts = sorted(posts, key=lambda x: x.get("id", 0), reverse=True)
    return render_template("feed.html", posts=posts)

@app.route("/post/<int:post_id>")
def post(post_id):
    posts = load_json(POSTS_FILE)
    item = next((p for p in posts if p.get("id") == post_id), None)
    if not item:
        abort(404, "Post not found")
    normalize_post(item)
    return render_template("post.html", post=item)

# -------------------- Add Post --------------------
@app.route("/addpost", methods=["GET", "POST"])
@login_required
def addpost():
    if request.method == "POST":
        user = get_current_user()
        posts = load_json(POSTS_FILE)

        caption  = (request.form.get("caption")  or "").strip()
        file = request.files.get("image_file")
        if not file or not file.filename:
            return "No image uploaded. Ensure the input is name='image_file' and form has enctype='multipart/form-data'.", 400
        if not allowed_file(file.filename):
            return "Invalid image type. Allowed: png, jpg, jpeg, gif, webp.", 400

        filename  = secure_filename(file.filename)
        file.save(os.path.join(POST_UPLOAD_DIR, filename))
        image_path = f"img/posts/{filename}"

        new_id = (posts[-1]["id"] + 1) if posts else 1
        new_post = {
            "id": new_id,
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
    new_id = (post["comments"][-1]["id"] + 1) if post["comments"] else 1
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    post["comments"].append({
        "id": new_id,
        "username": user["username"],
        "text": text,
        "ts": ts
    })
    save_posts(posts)
    return jsonify({"ok": True, "comment": {"id": new_id, "username": user["username"], "text": text, "ts": ts}, "count": len(post["comments"])})

# -------------------- Conferences --------------------
@app.route("/conferences")
def conferences():
    confs = load_json(CONF_FILE)
    return render_template("conferences.html", conferences=confs)

@app.route("/conference/<conf_id>")
def conference(conf_id):
    confs = load_json(CONF_FILE)
    conf = next((c for c in confs if c.get("id") == conf_id), None)
    if not conf:
        abort(404, "Conference not found")
    return render_template("conference.html", conference=conf)

@app.route("/addconference", methods=["GET", "POST"])
@login_required
def addconference():
    if request.method == "POST":
        confs = load_json(CONF_FILE)
        tags_raw = request.form.get("tags", "")

        file = request.files.get("banner_file")
        if not file or not file.filename:
            return "No banner uploaded. Ensure the input is name='banner_file' and form has enctype='multipart/form-data'.", 400
        if not allowed_file(file.filename):
            return "Invalid banner type. Allowed: png, jpg, jpeg, gif, webp.", 400

        filename  = secure_filename(file.filename)
        file.save(os.path.join(CONF_UPLOAD_DIR, filename))
        banner_path = f"img/conferences/{filename}"

        new_conf = {
            "id":   (request.form.get("id") or "").strip(),
            "name": (request.form.get("name") or "").strip(),
            "date": (request.form.get("date") or "").strip(),
            "location": (request.form.get("location") or "").strip(),
            "description": (request.form.get("description") or "").strip(),
            "banner": banner_path,
            "tags": [t.strip() for t in tags_raw.split(",")] if tags_raw else []
        }
        confs.append(new_conf)
        save_json(CONF_FILE, confs)
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
    posts = load_json(POSTS_FILE)
    user = find_user(users, username)
    if not user:
        abort(404, "User not found")
    user.setdefault("followers", [])
    user.setdefault("following", [])
    user_posts = [normalize_post(p) for p in posts if p.get("username") == username]
    return render_template("profile.html", user=user, posts=user_posts)

# -------------------- Forums --------------------
@app.route("/forums")
def forums():
    threads = load_json(FORUM_THREADS)
    q = (request.args.get("q") or "").strip().lower()
    tag = (request.args.get("tag") or "").strip().lower()

    if q:
        def hit(t):
            return q in (t.get("title","").lower() + " " + t.get("body","").lower() + " " + " ".join(t.get("tags",[])).lower())
        threads = [t for t in threads if hit(t)]
    if tag:
        threads = [t for t in threads if tag in [x.lower() for x in t.get("tags", [])]]

    threads = sorted(threads, key=lambda t: t.get("created_ts", 0), reverse=True)
    return render_template("forums.html", threads=threads, q=q, tag=tag)

@app.route("/forums/new", methods=["GET", "POST"])
@login_required
def forum_new():
    if request.method == "POST":
        me = get_current_user()
        threads = load_json(FORUM_THREADS)
        title = (request.form.get("title") or "").strip()
        body  = (request.form.get("body") or "").strip()
        tags_raw = (request.form.get("tags") or "").strip()

        if not title or not body:
            flash("Title and body are required.", "error")
            return redirect(url_for("forum_new"))

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
    replies = load_json(FORUM_REPLIES)

    thread = next((t for t in threads if t.get("slug") == slug or str(t.get("id")) == slug), None)
    if not thread:
        abort(404, "Thread not found")

    # increment views
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

        rid = next_id(replies)
        reply = {
            "id": rid,
            "thread_id": thread["id"],
            "author": me["username"],
            "text": text,
            "created_ts": int(time.time())
        }
        replies.append(reply)
        save_json(FORUM_REPLIES, replies)

        thread["replies"] = int(thread.get("replies", 0)) + 1
        save_json(FORUM_THREADS, threads)

        return redirect(url_for("forum_thread", slug=slug))

    thread_replies = [r for r in replies if r.get("thread_id") == thread["id"]]
    thread_replies = sorted(thread_replies, key=lambda r: r.get("created_ts", 0))
    return render_template("forum_thread.html", thread=thread, replies=thread_replies)

# -------------------- Platformer (T-Rex-like) --------------------
@app.route("/platformer")
def platformer():
    return render_template("platformer.html")

# -------------------- About --------------------
@app.route("/about")
def about():
    return render_template("about.html")

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
    try: info["post_files"] = sorted(os.listdir(POST_UPLOAD_DIR))
    except Exception as e: info["post_files"] = [f"<error: {e}>"]
    try: info["user_files"] = sorted(os.listdir(USER_UPLOAD_DIR))
    except Exception as e: info["user_files"] = [f"<error: {e}>"]
    try: info["conference_files"] = sorted(os.listdir(CONF_UPLOAD_DIR))
    except Exception as e: info["conference_files"] = [f"<error: {e}>"]
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
