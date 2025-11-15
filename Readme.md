

# 🌍 **Muniverse — A Modern Social Platform for MUN Students**

**Live Deployment:** [https://www.muniverse.social](https://www.muniverse.social)
**Tech Stack:** Flask • Jinja2 • JSON Storage • HTML/CSS/JS • Static Asset Uploads
**Status:** Active Development 🚀

Muniverse is a lightweight social platform designed specifically for **Model United Nations (MUN)** students and conferences.
It includes user profiles, a feed with image posts, comments, likes, a forum, conference listings, an admin portal, and more — all built without a database, using clean JSON storage for maximum portability.

---

## ✨ **Key Features**

### 👤 **User Accounts & Profiles**

* Sign up with username, name, school, bio, and profile picture
* Secure password hashing using `werkzeug.security`
* View other user profiles
* Follow/unfollow any user

---

### 🖼️ **Posting System**

* Create posts with captions + images
* **Automatic image cropping & compression** (Instagram 4:5 ratio, auto-compressed under 400 KB)
* Like/unlike posts (AJAX API)
* Comment on posts (AJAX API)
* Edit or delete your posts
* Explore page with search

---

### 💬 **Forums**

* Create discussion threads
* Replies with timestamps
* Tag-based filtering
* View count tracking
* Clean, readable MUN-style discussion layout

---

### 🎓 **Conferences**

* Browse all MUN conferences
* Each conference has:

  * Name
  * Date
  * Location
  * Description
  * Tags
  * Banner image
* Admin workflow to approve conferences

---

### 🛡️ **Admin Portal**

Admin users can:

* Approve conference submissions
* View platform insights (posts, likes, comments, top users)
* Delete posts
* Delete users
* Promote/demote admins
* Filter/search users

Admin route:

```
/admin
```

Access requires:

```
user.role = "admin"
```

---

### 🔒 **Security**

* CSRF-safe forms (POST routes)
* Passwords hashed using `generate_password_hash`
* Upload validation (filetype & size)
* Sanitized filenames with `secure_filename`
* Session-protected routes
* Admin gatekeeping is enforced server-side

---

## 🏛️ **Project Structure**

```
MUNIVERSE/
│
├── app.py                # Main Flask application
├── requirements.txt      # Dependencies
├── Procfile              # For Koyeb/Heroku-like deployment
│
├── templates/            # All HTML templates
│   ├── login.html
│   ├── signup.html
│   ├── feed.html
│   ├── explore.html
│   ├── addpost.html
│   ├── forums.html
│   ├── forum_thread.html
│   ├── conferences.html
│   ├── addconference.html
│   └── adminportal.html
│
├── static/
│   ├── css/style.css
│   ├── img/users/
│   ├── img/posts/
│   └── img/conferences/
│
└── data/                 # JSON-based storage system
    ├── users.json
    ├── posts.json
    ├── conferences.json
    ├── forum_threads.json
    └── forum_replies.json
```

This repo **does not require a database**, making deployment extremely fast & portable.

---

## 🚀 **Local Development Setup**

### 1️⃣ Clone the project

```bash
git clone https://github.com/yourname/muniverse.git
cd muniverse
```

### 2️⃣ Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Create data directory

```bash
mkdir -p data
echo "[]" > data/users.json
echo "[]" > data/posts.json
echo "[]" > data/conferences.json
echo "[]" > data/forum_threads.json
echo "[]" > data/forum_replies.json
```

### 5️⃣ Run the development server

```bash
python app.py
```

Access at:

```
http://127.0.0.1:5000
```

---

## 🔑 **Environment Variables**

Muniverse supports an optional secret key:

| Variable           | Purpose                  |
| ------------------ | ------------------------ |
| `MUNIVERSE_SECRET` | Flask session secret key |

Example:

```bash
export MUNIVERSE_SECRET="mysecretkey123"
```

---

## 🌐 **Deployment Guide**

### ✔️ **Recommended Host: KOYEB (Free, No Sleep)**

Koyeb is the best free host for Flask apps.
**Muniverse is fully compatible.**

### Required File: **Procfile**

```
web: gunicorn app:app
```

### Add these build/runtime settings:

* **Buildpack:** Python
* **Run command:** auto-detected from Procfile
* **Expose port:** `$PORT` (Koyeb does this automatically)

Koyeb URL → connect custom domain →
**[www.muniverse.social](http://www.muniverse.social)** ✔️

---

### ✔️ Deploying on Railway

```
railway init
railway up
```

Railway auto-detects Python + Procfile.

---

### ✔️ Deploying on Render

Render → Web Service → Python
Add run command:

```
gunicorn app:app
```

---

### ⚠️ Not recommended: Vercel

Vercel does *not* support long-running Python processes without a serverless rewrite.

---

## 📦 **Static Uploads Behavior**

All user-uploaded images are stored inside:

```
/static/img/users/
/static/img/posts/
/static/img/conferences/
```

Each upload is validated:

* File extension
* Size limit
* Sanitized name
* Replaced if same username uploads new profile pic

---

## 📊 **Admin Stats & Insights**

Admin dashboard includes:

* Total users
* Total posts
* Total comments
* Total likes
* Top 10 users by likes
* Top posts
* Full user table with tools
* Full posts table with admin actions

---

## ✉️ **Conference Approval Workflow**

When a user submits a conference:

1. It is saved to `pending_conferences.json`
2. Admin sees approval buttons
3. Admin can approve → moves to `conferences.json`
4. Admin can reject → deletes the entry

---

## 🛠️ **Roadmap (Future Features)**

* 🧵 Real-time chatrooms
* 🔔 Notifications system
* 🌒 Dark mode toggle
* 💾 Switch from JSON → SQLite/Firestore
* 📱 PWA mobile app
* 🌐 API endpoints for mobile clients

---

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch

   ```
   git checkout -b feature/my-feature
   ```
3. Commit changes
4. Push and submit a PR

We welcome contributions from students & developers!

---

## 🐞 **Troubleshooting**

### ❌ Admin seeing `_stats` error

Your users JSON file needs these defaults:

```json
"followers": [],
"following": []
```

Also make sure you are visiting:

```
/admin
```

as an admin user.

### ❌ Koyeb “No Command To Run”

You must include:

**Procfile**

```
web: gunicorn app:app
```

---

## 🧑‍🚀 **Built By**

A collaborative project designed for the global MUN community.
Modern, secure, student-friendly, and clean.

---

## ⭐ **Support Muniverse**

If you like this project, star it on GitHub and share it with MUNers worldwide!


