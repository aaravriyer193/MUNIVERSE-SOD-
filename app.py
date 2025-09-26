from flask import Flask, render_template, request, redirect, url_for, abort
from werkzeug.utils import secure_filename
import json, os

# -----------------------------------------------------------------------------
# Flask setup (explicit folders)
# -----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")

# -----------------------------------------------------------------------------
# Data paths
# -----------------------------------------------------------------------------
DATA_DIR   = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
POSTS_FILE = os.path.join(DATA_DIR, "posts.json")
CONF_FILE  = os.path.join(DATA_DIR, "conferences.json")

os.makedirs(DATA_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# Uploads (absolute paths inside /static)
# -----------------------------------------------------------------------------
POST_UPLOAD_DIR = os.path.join(app.static_folder, "img", "posts")
USER_IMG_DIR    = os.path.join(app.static_folder, "img", "users")
CONF_UPLOAD_DIR = os.path.join(app.static_folder, "img", "conferences")
for d in (POST_UPLOAD_DIR, USER_IMG_DIR, CONF_UPLOAD_DIR):
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

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def onboarding():
    return render_template("onboarding.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users = load_json(USERS_FILE)
        username = (request.form.get("username") or "").strip()

        new_user = {
            "name":   (request.form.get("name") or "").strip(),
            "username": username,
            "school": (request.form.get("school") or "").strip(),
            "bio":    (request.form.get("bio") or "").strip(),
            # convention: img/users/<username>.jpg (you place file manually or add upload later)
            "profile_pic": f"img/users/{username}.jpg" if username else "",
            "attendingConferences": []
        }
        users.append(new_user)
        save_json(USERS_FILE, users)
        return redirect(url_for("feed"))
    return render_template("signup.html")

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

# ---------- addpost (no underscore), with file upload ----------
@app.route("/addpost", methods=["GET", "POST"])
def addpost():
    if request.method == "POST":
        posts = load_json(POSTS_FILE)

        username = (request.form.get("username") or "").strip()
        caption  = (request.form.get("caption")  or "").strip()

        # File upload (required)
        file = request.files.get("image_file")
        if not file or not file.filename:
            return "No image uploaded. Ensure the input is name='image_file' and form has enctype='multipart/form-data'.", 400
        if not allowed_file(file.filename):
            return "Invalid image type. Allowed: png, jpg, jpeg, gif, webp.", 400

        filename  = secure_filename(file.filename)
        save_path = os.path.join(POST_UPLOAD_DIR, filename)
        file.save(save_path)

        image_path = f"img/posts/{filename}"  # JSON path (used with url_for('static', filename=...))

        new_id = (posts[-1]["id"] + 1) if posts else 1
        new_post = {
            "id": new_id,
            "username": username,
            "caption": caption,
            "image": image_path,
            "likes": 0,
            "comments": []
        }
        posts.append(new_post)
        save_json(POSTS_FILE, posts)
        return redirect(url_for("feed"))

    return render_template("addpost.html")

@app.route("/explore")
def explore():
    posts = load_json(POSTS_FILE)
    return render_template("explore.html", posts=posts)

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

# ---------- addconference (no underscore), with file upload ----------
@app.route("/addconference", methods=["GET", "POST"])
def addconference():
    if request.method == "POST":
        confs = load_json(CONF_FILE)
        tags_raw = request.form.get("tags", "")

        # File upload (required)
        file = request.files.get("banner_file")
        if not file or not file.filename:
            return "No banner uploaded. Ensure the input is name='banner_file' and form has enctype='multipart/form-data'.", 400
        if not allowed_file(file.filename):
            return "Invalid banner type. Allowed: png, jpg, jpeg, gif, webp.", 400

        filename  = secure_filename(file.filename)
        save_path = os.path.join(CONF_UPLOAD_DIR, filename)
        file.save(save_path)

        banner_path = f"img/conferences/{filename}"  # JSON path (used with url_for('static', filename=...))

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

@app.route("/profile/<username>")
def profile(username):
    users = load_json(USERS_FILE)
    posts = load_json(POSTS_FILE)
    user = next((u for u in users if u.get("username") == username), None)
    if not user:
        abort(404, "User not found")
    user_posts = [p for p in posts if p.get("username") == username]
    return render_template("profile.html", user=user, posts=user_posts)

@app.route("/about")
def about():
    return render_template("about.html")

# ---------- tiny debug endpoint to verify uploads ----------
@app.route("/_uploads")
def _uploads():
    info = {
        "static_folder": app.static_folder,
        "POST_UPLOAD_DIR": POST_UPLOAD_DIR,
        "CONF_UPLOAD_DIR": CONF_UPLOAD_DIR,
        "post_files": [],
        "conference_files": []
    }
    try:
        info["post_files"] = sorted(os.listdir(POST_UPLOAD_DIR))
    except Exception as e:
        info["post_files"] = [f"<error: {e}>"]
    try:
        info["conference_files"] = sorted(os.listdir(CONF_UPLOAD_DIR))
    except Exception as e:
        info["conference_files"] = [f"<error: {e}>"]
    return info

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("ROOT:", app.root_path)
    print("TEMPLATES:", os.path.join(app.root_path, app.template_folder))
    print("STATIC:", os.path.join(app.root_path, app.static_folder))
    app.run(debug=True)
