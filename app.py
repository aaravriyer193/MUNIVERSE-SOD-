from flask import Flask, render_template, request, redirect, url_for, abort
import json, os

app = Flask(__name__)

# ---------- File Paths ----------
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
POSTS_FILE = os.path.join(DATA_DIR, "posts.json")
CONF_FILE = os.path.join(DATA_DIR, "conferences.json")


# ---------- Helpers ----------
def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------- Routes ----------

@app.route("/")
def onboarding():
    return render_template("onboarding.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users = load_json(USERS_FILE)
        new_user = {
            "name": request.form["name"],
            "username": request.form["username"],
            "school": request.form["school"],
            "bio": request.form["bio"],
            "profile_pic": f"img/users/{request.form['username']}.jpg",
            "attendingConferences": []
        }
        users.append(new_user)
        save_json(USERS_FILE, users)
        return redirect(url_for("feed"))
    return render_template("signup.html")


@app.route("/feed")
def feed():
    posts = load_json(POSTS_FILE)
    posts = sorted(posts, key=lambda x: x["id"], reverse=True)
    return render_template("feed.html", posts=posts)


@app.route("/post/<int:post_id>")
def post(post_id):
    posts = load_json(POSTS_FILE)
    post = next((p for p in posts if p["id"] == post_id), None)
    if not post:
        abort(404, "Post not found")
    return render_template("post.html", post=post)


@app.route("/add_post", methods=["GET", "POST"])
def add_post():
    if request.method == "POST":
        posts = load_json(POSTS_FILE)
        new_post = {
            "id": len(posts) + 1,
            "username": request.form["username"],
            "caption": request.form["caption"],
            "image": f"img/posts/{request.form['image']}",
            "likes": 0,
            "comments": []
        }
        posts.append(new_post)
        save_json(POSTS_FILE, posts)
        return redirect(url_for("feed"))
    return render_template("add_post.html")


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
    conf = next((c for c in confs if c["id"] == conf_id), None)
    if not conf:
        abort(404, "Conference not found")
    return render_template("conference.html", conference=conf)


@app.route("/add_conference", methods=["GET", "POST"])
def add_conference():
    if request.method == "POST":
        confs = load_json(CONF_FILE)
        new_conf = {
            "id": request.form["id"],
            "name": request.form["name"],
            "date": request.form["date"],
            "location": request.form["location"],
            "description": request.form["description"],
            "banner": f"img/conferences/{request.form['banner']}",
            "tags": [tag.strip() for tag in request.form["tags"].split(",")]
        }
        confs.append(new_conf)
        save_json(CONF_FILE, confs)
        return redirect(url_for("conferences"))
    return render_template("add_conference.html")


@app.route("/profile/<username>")
def profile(username):
    users = load_json(USERS_FILE)
    posts = load_json(POSTS_FILE)
    user = next((u for u in users if u["username"] == username), None)
    if not user:
        abort(404, "User not found")
    user_posts = [p for p in posts if p["username"] == username]
    return render_template("profile.html", user=user, posts=user_posts)


@app.route("/about")
def about():
    return render_template("about.html")


# ---------- Run ----------
if __name__ == "__main__":
    app.run(debug=True)
