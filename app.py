from flask import (
    Flask, render_template, request, redirect,
    url_for, abort, session, flash, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import json, os, functools

# -----------------------------------------------------------------------------
# Flask setup
# -----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("MUNIVERSE_SECRET", "dev-change-me")

# -----------------------------------------------------------------------------
# Data paths
# -----------------------------------------------------------------------------
DATA_DIR   = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
POSTS_FILE = os.path.join(DATA_DIR, "posts.json")
CONF_FILE  = os.path.join(DATA_DIR, "conferences.json")
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

        # profile photo (required)
        file = request.files.get("profile_photo")
        if not file or not file.filename:
            flash("Please upload a profile photo.", "error")
            return redirect(url_for("signup"))
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
            "followers": [],   # list of usernames following this user
            "following": []    # list of usernames this user follows
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

# -------------------- Feed / Posts --------------------
@app.route("/explore")
def explore():
    """Simple explore page with optional ?q= search."""
    posts = load_json(POSTS_FILE)
    q = (request.args.get("q") or "").strip().lower()

    if q:
        def hit(p):
            cap = (p.get("caption") or "").lower()
            user = (p.get("username") or "").lower()
            return q in cap or q in user
        posts = [p for p in posts if hit(p)]

    # newest first
    posts = sorted(posts, key=lambda x: x.get("id", 0), reverse=True)
    return render_template("explore.html", posts=posts, q=q)
@app.route("/feed")
def feed():
    posts = load_json(POSTS_FILE)
    posts = sorted(posts, key=lambda x: x.get("id", 0), reverse=True)
    return render_template("feed.html", posts=posts)

@app.route("/post/<int:post_id>")
def post(post_id):
    posts = load_json(POSTS_FILE)
    item = next((p for p in posts if p.get("id") == post_id), None)
    if not item:
        abort(404, "Post not found")
    return render_template("post.html", post=item)

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
            "comments": []
        }
        posts.append(new_post)
        save_json(POSTS_FILE, posts)
        return redirect(url_for("feed"))

    return render_template("addpost.html")

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

    # initialize fields if missing (for older data)
    me.setdefault("following", [])
    other.setdefault("followers", [])

    if username in me["following"]:
        # UNFOLLOW
        me["following"].remove(username)
        if me_name in other["followers"]:
            other["followers"].remove(me_name)
        action = "unfollowed"
    else:
        # FOLLOW
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
    user_posts = [p for p in posts if p.get("username") == username]
    return render_template("profile.html", user=user, posts=user_posts)

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
        "post_files": [],
        "user_files": [],
        "conference_files": []
    }
    try: info["post_files"] = sorted(os.listdir(POST_UPLOAD_DIR))
    except Exception as e: info["post_files"] = [f"<error: {e}>"]
    try: info["user_files"] = sorted(os.listdir(USER_UPLOAD_DIR))
    except Exception as e: info["user_files"] = [f"<error: {e}>"]
    try: info["conference_files"] = sorted(os.listdir(CONF_UPLOAD_DIR))
    except Exception as e: info["conference_files"] = [f"<error: {e}>"]
    return info

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("ROOT:", app.root_path)
    print("TEMPLATES:", os.path.join(app.root_path, app.template_folder))
    print("STATIC:", os.path.join(app.root_path, app.static_folder))
    app.run(debug=True)
