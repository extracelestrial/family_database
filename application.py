from collections import namedtuple
from datetime import datetime
from sqlite3 import Row, connect
from tempfile import mkdtemp

import pandas as pd
from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from graphviz import Digraph
from werkzeug.exceptions import HTTPException, InternalServerError, default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Connect to SQLite database
db = connect("info.db", check_same_thread=False)
db.row_factory = Row
cur = db.cursor()


@app.route("/")
@login_required
def index():
    cur.execute("SELECT * FROM info WHERE announcements IS NOT NULL AND announcements != ''")

    announcements = []
    row = namedtuple('row', ['name', 'announcement'])

    for item in cur:
        name = item['first'] + ' '
        if item['maiden'] != '':
            name += item['maiden'] + " "
        name += item['last']

        announcement = row(name, item['announcements'])
        announcements.append(announcement)

    return render_template("index.html", announcements=announcements)


@app.route("/tree")
def tree():         # Ref. https://medium.com/@ahsenparwez/building-a-family-tree-with-python-and-graphviz-e4afb8367316
    # Capture all info in dataframe
    family_tree = pd.read_sql("SELECT * FROM info ORDER BY birthdate", db)
    family_tree['recorded_ind'] = 0  # Flag for indicating individuals whose data has been recorded in the tree
    earl_ans = family_tree.loc[family_tree['relationship'] == 'root'].iloc[0]
    incomp = [earl_ans['id']]
    comp = []

    # Initialize graph and list of nodes
    dot = Digraph(comment='Family Tree', graph_attr={'splines': 'true', 'ranksep': '0.7', 'rankdir': 'LR',
                                                     'ratio': '3'})

    # Initialize first node (root)
    sh = 'oval'
    node_id = str(earl_ans['id'])
    node_name = f"{earl_ans['first']} {earl_ans['last']}"
    color = '#c0c0c0' if earl_ans['deceased'] else '#ffffff'
    dot.node(node_id, node_name, shape=sh, style='filled', fillcolor=color)
    node_nm = [earl_ans]

    # Set recorded flag to 1
    family_tree.loc[family_tree['id'] == earl_ans['id'], ['recorded_ind']] = 1

    # max_iter should be greater than number of generations
    max_iter = 5

    for _ in range(max_iter):
        temp = family_tree[family_tree['recorded_ind'] == 0]

        if len(temp) == 0:      # Break loop when all individuals have been recorded
            break
        temp['this_gen_ind'] = temp.apply(lambda x: 1 if x['person2'] in incomp else 0, axis=1)

        # Spouse Relationship
        this_gen = temp[(temp['this_gen_ind'] == 1) & (temp['relationship'] == 'spouse')]
        if len(this_gen) > 0:
            for j in range(len(this_gen)):
                per1 = this_gen.iloc[j]
                per1_id = str(per1['id'])
                per1_name = f"{per1['first']} {per1['last']}"
                per2 = str(int(per1['person2']))
                color = '#c0c0c0' if per1['deceased'] else '#add8e6'
                sh = 'oval'
                with dot.subgraph() as subs:
                    subs.attr(rank='same')
                    subs.node(per1_id, per1_name, shape=sh, style='filled', fillcolor=color)
                    node_nm.append(per1)
                    subs.edge(per2, per1_id, arrowhead='none', color="black:invis:black")

        # Child Relationship
        this_gen = temp[(temp['this_gen_ind'] == 1) & (temp['relationship'] == 'child')]
        if len(this_gen) > 0:
            sh = 'oval'
            for j in range(len(this_gen)):
                per1 = this_gen.iloc[j]
                per1_id = str(per1['id'])
                per1_name = f"{per1['first']} {per1['last']}"
                per2 = str(int(per1['person2']))
                color = '#c0c0c0' if per1['deceased'] else '#caeccd'
                with dot.subgraph() as subs:
                    subs.node(per1_id, per1_name, shape=sh, style='filled', fillcolor=color)
                    node_nm.append(per1)
                    subs.edge(per2, per1_id)

        comp.extend(incomp)
        incomp = list(temp.loc[temp['this_gen_ind'] == 1, 'id'])
        family_tree['recorded_ind'] = temp.apply(lambda x: 1 if (x['id'] in incomp) | (x['id'] in comp) else 0,
                                                 axis=1)

    dot.format = 'svg'
    dot.render('static/family_tree')

    return render_template("tree.html")


@app.route("/me", methods=["GET", "POST"])
def me():
    """View an edit current user's information"""

    # User reached outer via POST (as by submitting a form via POST)
    username = session["user_id"]
    if request.method == "POST":
        # Determine current user's id
        cur.execute("SELECT info.id FROM info JOIN users ON info.user_id = users.id WHERE username = ?", (
                    username,))
        for row in cur:
            user_id = row['id']

        for field in ['first', 'middle', 'maiden', 'last', 'birthdate',
                      'anniversary', 'address', 'homephone', 'cellphone',
                      'workphone', 'email', 'altemail', 'website',
                      'announcements']:

            # set current field to updated info
            updateInfo = request.form.get(field)
            cur.execute(f'UPDATE info SET {field} = ? WHERE id = ?', (updateInfo, user_id))
        db.commit()
        return redirect("/me")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        cur.execute("SELECT * FROM info JOIN users ON info.user_id = users.id WHERE username = ?", (username,))

        person = namedtuple('person', ['first', 'middle', 'maiden', 'last', 'birthdate', 'anniversary', 'address',
                            'homephone', 'cellphone', 'workphone', 'email', 'altemail', 'website', 'announcements'])
        for row in cur:
            member = person(row['first'], row['middle'], row['maiden'],
                            row['last'], row['birthdate'], row['anniversary'],
                            row['address'], row['homephone'], row['cellphone'],
                            row['workphone'], row['email'], row['altemail'],
                            row['website'], row['announcements'])

        return render_template("me.html", user=member)


@app.route("/lookup", methods=["GET", "POST"])
def lookup():
    """Lookup family member information"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method != "POST":
        return render_template("lookup.html")
    # User reached outer via POST (as by submitting a form via POST)
    firstName = request.form.get("firstName")
    lastName = request.form.get("lastName")
    search_name = firstName.capitalize() + " " + lastName.capitalize()

    cur.execute(f"SELECT * FROM info WHERE first LIKE '%{firstName}%' AND (last LIKE '%{lastName}%'"
                f"OR maiden LIKE '%{lastName}%')")

    # if not len(cur.fetchall()):
    #     return apology("no results found", 403)

    people = []
    person = namedtuple('person', ['id', 'name', 'birthdate'])

    for row in cur:
        name = row['first'] + ' ' + row['last']

        if not row['birthdate']:
            birthdate = '-'
        else:
            birthdate_string = row['birthdate']
            birthdate = datetime.strptime(birthdate_string, "%Y-%m-%d")
            birthdate = birthdate.strftime("%B %-d, %Y")

        member = person(row['id'], name, birthdate)
        people.append(member)

    if len(people) == 1:
        return redirect(f'/profile/{people[0].id}')

    return render_template("lookup_result.html", search_name=search_name, people=people)


@app.route("/export", methods=["GET", "POST"])
def export():
    """Export family member information"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method != "POST":
        return render_template("export.html")
    # User reached outer via POST (as by submitting a form via POST)
    options = ['check1', 'check2', 'check3', 'check4', 'check5', 'check6', 'check7',
               'check8', 'check9', 'check10', 'check11', 'check12', 'check13', 'check14']
    for option in options:
        print(request.form.get(option))
    options_selected = [option for option in options if request.form.get(option)]
    cur.execute(f"SELECT {', '.join(options_selected)} FROM info")
    # cur.execute("SELECT * FROM info")
    df = pd.DataFrame(cur.fetchall())
    colnames = [desc[0] for desc in cur.description]
    with open('test.csv', 'w') as f:
        df.to_csv(f, header=colnames)

    return render_template("export.html")


@app.route("/profile/<person_id>")
def profile(person_id):
    cur.execute("SELECT * FROM info WHERE id = ?", [person_id])

    person = namedtuple('person', ['name', 'birthdate', 'deceased', 'age',
                                   'anniversary', 'address', 'homephone',
                                   'cellphone', 'workphone', 'email',
                                   'altemail', 'website', 'announcements'])
    for row in cur:
        name = row['first'] + " "
        if row['middle'] != '':
            name += row['middle'] + " "
        if row['maiden'] != '':
            name += row['maiden'] + " "
        name += row['last']

        if row['birthdate']:
            birthdate_string = row['birthdate']
            birthdate_datetime = datetime.strptime(birthdate_string, "%Y-%m-%d")
            birthdate = birthdate_datetime.strftime("%B %-d, %Y")
        else:
            birthdate = '-'

        if row['deceased']:
            deceased_string = row['deceased']
            deceased_datetime = datetime.strptime(deceased_string, "%Y-%m-%d")
            deceased = deceased_datetime.strftime("%B %-d, %Y")
            age = deceased_datetime.year - birthdate_datetime.year
            if deceased_datetime.month < birthdate_datetime.month or (deceased_datetime.month ==
                                                                      birthdate_datetime.month and
                                                                      deceased_datetime.day < birthdate_datetime.day):
                age -= 1
        else:
            deceased = '-'
            today = datetime.now()
            age = today.year - birthdate_datetime.year
            if today.month < birthdate_datetime.month or (today.month == birthdate_datetime.month and today.day <
                                                          birthdate_datetime.day):
                age -= 1

        if row['anniversary']:
            anniversary = datetime.strptime(row['anniversary'], "%Y-%m-%d")
            anniversary = anniversary.strftime("%B %-d, %Y")
        else:
            anniversary = '-'
        member = person(name, birthdate, deceased, age, anniversary,
                        row['address'], row['homephone'], row['cellphone'],
                        row['workphone'], row['email'], row['altemail'],
                        row['website'], row['announcements'])

    return render_template("profile.html", person=member)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method != "POST":
        return render_template("login.html")

    # User reached route via POST (as by submitting a form via POST)
    # Ensure username was submitted
    if not request.form.get("username"):
        return apology("must provide username", 403)

    # Ensure password was submitted
    elif not request.form.get("password"):
        return apology("must provide password", 403)

    # Query database for username
    username = request.form.get("username")

    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    rows = cur.fetchone()

    # Ensure username exists and password is correct
    if rows is None:
        return apology("invalid username", 403)
    if not check_password_hash(rows[-1], request.form.get("password")):
        return apology("invalid password", 403)

    # Remember which user has logged in
    session["user_id"] = rows[1]

    # Redirect user to home page
    return redirect("/")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method != "POST":
        return render_template("register.html")

    # User reached route via POST (as by submitting a form via POST)
    username = request.form.get("username")

    cur.execute("SELECT * FROM users WHERE username = ?;", (username,))
    rows = cur.fetchone()

    # Ensure username was submitted
    if not request.form.get("username"):
        return apology("must provide username", 403)

    # Ensure username doesn't already exist
    elif rows is not None:
        return apology("username already exists", 403)

    # Ensure password was submitted
    elif not request.form.get("password"):
        return apology("must provide password", 403)

    # Ensure password confirmation matches password
    elif request.form.get("password") != request.form.get("confirmation"):
        return apology("password does not match", 403)

    # Insert new user into users
    else:
        username = request.form.get("username")
        password_hash = generate_password_hash(request.form.get("password"))

        cur.execute("INSERT INTO users (username, hash) VALUES(?, ?);", (username, password_hash))
        db.commit()

        # Redirect user to home page
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

if __name__ == '__main__':
    # app.run('0.0.0.0')
    app.run()           # For development
