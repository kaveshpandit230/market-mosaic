from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3, os, json, secrets, csv, io
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production-please')
# On Railway/Render, use /tmp for writable storage (ephemeral — resets on redeploy)
# For persistent data, upgrade to Railway's PostgreSQL or Render's Postgres add-on
DB = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'market_mosaic.db'))
if os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER'):
    DB = '/tmp/market_mosaic.db'

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, company TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                plan TEXT DEFAULT 'free', is_admin INTEGER DEFAULT 0,
                api_key TEXT UNIQUE, phone TEXT,
                notif_app INTEGER DEFAULT 1,
                notif_whatsapp INTEGER DEFAULT 0,
                notif_sms INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, name TEXT NOT NULL, channel TEXT NOT NULL,
                status TEXT DEFAULT 'draft', budget REAL DEFAULT 0, spent REAL DEFAULT 0,
                impressions INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0, notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL,
                company TEXT, phone TEXT, status TEXT DEFAULT 'new',
                source TEXT DEFAULT 'organic', notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL, used INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, message TEXT NOT NULL,
                read INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id TEXT,
                payment_id TEXT,
                plan TEXT NOT NULL,
                amount REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        ''')

init_db()

# ── HELPERS ───────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            flash('Please log in.', 'error'); return redirect(url_for('login'))
        return f(*a, **kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session: return redirect(url_for('login'))
        u = get_current_user()
        if not u or not u['is_admin']:
            flash('Access denied.', 'error'); return redirect(url_for('dashboard'))
        return f(*a, **kw)
    return d

def get_current_user():
    if 'user_id' in session:
        with get_db() as db:
            return db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    return None

def add_notification(uid, msg):
    with get_db() as db:
        db.execute('INSERT INTO notifications (user_id,message) VALUES (?,?)', (uid, msg))

def unread(uid):
    with get_db() as db:
        return db.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0', (uid,)).fetchone()[0]

def api_auth():
    key = request.headers.get('X-API-Key') or request.args.get('api_key')
    if not key: return None
    with get_db() as db:
        return db.execute('SELECT * FROM users WHERE api_key=?', (key,)).fetchone()

# ── PUBLIC ────────────────────────────────────────────────
@app.route('/'); 
def home(): return render_template('home.html', user=get_current_user())

@app.route('/about')
def about(): return render_template('about.html', user=get_current_user())

@app.route('/services')
def services(): return render_template('services.html', user=get_current_user())

@app.route('/pricing')
def pricing(): return render_template('pricing.html', user=get_current_user())

@app.route('/contact', methods=['GET','POST'])
def contact():
    if request.method == 'POST':
        flash("Thanks! We'll be in touch within 24 hours.", 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html', user=get_current_user())

# ── BLOG ──────────────────────────────────────────────────
BLOG_POSTS = [
    {'slug':'brand-identity-india-2026','title':'What Makes a Brand Identity Work in India in 2026',
     'tag':'Brand Strategy','date':'March 10, 2026','author':'Saira Mehta',
     'excerpt':'Indian consumers are more brand-literate than ever. Here is what separates the brands that stick from the ones that fade.',
     'icon':'◎','bg':'linear-gradient(135deg,#f0ebe2,#e0d5c4)',
     'content':'''<p>India's brand landscape has shifted dramatically. A decade ago, a recognisable logo and a catchy jingle were enough. Today, consumers expect authenticity, visual coherence, and a brand that reflects their values.</p>
<h2>The Trust Deficit</h2><p>Indian consumers distrust advertising at higher rates than global counterparts. The brands that win lead with proof: customer stories, transparent sourcing, and consistent delivery.</p>
<blockquote>A brand is not what you say it is. It is what your customers say when you are not in the room.</blockquote>
<h2>Visual Identity That Travels</h2><p>With mobile-first consumption the norm, brand identities must work at thumbnail size and on a billboard alike. Complexity is the enemy.</p>
<h3>What to prioritise:</h3><ul><li>A wordmark that reads clearly at 32px</li><li>A colour palette of no more than three colours</li><li>Typography that is distinctive without being illegible</li></ul>
<p>At Market Mosaic, every brand identity engagement begins with a positioning workshop before a single pixel is placed.</p>'''},
    {'slug':'digital-marketing-roi-smes','title':'How Indian SMEs Can Get Real ROI from Digital Marketing',
     'tag':'Digital Marketing','date':'February 22, 2026','author':'Rohan Kapoor',
     'excerpt':'Most small businesses waste their digital marketing budgets. Here is the framework we use to turn Rs 1 into Rs 5.',
     'icon':'△','bg':'linear-gradient(135deg,#e8e4dd,#d8cfc2)',
     'content':'''<p>Digital marketing promises are seductive. The reality for most Indian SMEs is far messier — scattered spend, unclear attribution, and agencies that report vanity metrics instead of revenue.</p>
<h2>The Three Mistakes SMEs Make</h2>
<h3>1. Channels before customers</h3><p>The first question should never be "should we run Instagram ads?" It should be "where does our customer spend their attention?"</p>
<h3>2. Awareness and conversion as one campaign</h3><p>A first-time visitor and a returning prospect need fundamentally different messages.</p>
<h3>3. Measuring clicks instead of cash</h3><p>Revenue is the metric. Build reporting around spend-to-sale, not spend-to-engagement.</p>
<blockquote>If you cannot draw a line from your marketing activity to a business outcome, you have activity — not strategy.</blockquote>
<ul><li>Fix your conversion rate before scaling spend</li><li>Start with retargeting before prospecting</li><li>Run campaigns for at least 90 days before drawing conclusions</li></ul>'''},
    {'slug':'content-marketing-2026','title':'Content Marketing in 2026: What Still Works',
     'tag':'Content','date':'January 15, 2026','author':'Ananya Iyer',
     'excerpt':'AI has flooded the internet with mediocre content. Here is how to stand out by doing the opposite of everyone else.',
     'icon':'□','bg':'linear-gradient(135deg,#f2ede6,#e6ddd0)',
     'content':'''<p>The content marketing playbook that worked in 2020 is broken. AI-generated articles have made the internet noisier than ever. This creates an enormous opportunity for brands willing to invest in genuine, human-led content.</p>
<h2>What Has Not Changed</h2><p>People still want to learn, be entertained, and feel seen. Original insight and a genuine point of view are more valuable now than ever — precisely because they are so rare.</p>
<h2>The New Rules</h2>
<h3>Depth over frequency</h3><p>One genuinely useful piece outperforms ten generic posts every time.</p>
<h3>First-person perspective</h3><p>AI cannot have an experience. Your founder's perspective and your customers' stories are irreplaceable assets.</p>
<blockquote>Create content you would actually want to read. Then tell everyone you know about it.</blockquote>
<ul><li>One long-form piece per month beats daily short-form</li><li>Repurpose: one article becomes five LinkedIn posts, one email, one video</li><li>Build an email list — it is the only audience you own</li></ul>'''},
]

@app.route('/blog')
def blog(): return render_template('blog.html', user=get_current_user(), posts=BLOG_POSTS)

@app.route('/blog/<slug>')
def blog_post(slug):
    post = next((p for p in BLOG_POSTS if p['slug']==slug), None)
    if not post: flash('Post not found.','error'); return redirect(url_for('blog'))
    return render_template('blog_post.html', user=get_current_user(), post=post)

# ── AUTH ──────────────────────────────────────────────────
@app.route('/signup', methods=['GET','POST'])
def signup():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name=request.form.get('name','').strip(); company=request.form.get('company','').strip()
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        confirm=request.form.get('confirm','')
        if not all([name,company,email,password]): flash('All fields are required.','error')
        elif password!=confirm: flash('Passwords do not match.','error')
        elif len(password)<8: flash('Password must be at least 8 characters.','error')
        else:
            try:
                api_key='mm_'+secrets.token_hex(24)
                with get_db() as db:
                    db.execute('INSERT INTO users (name,company,email,password,api_key) VALUES (?,?,?,?,?)',
                               (name,company,email,generate_password_hash(password),api_key))
                    user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                    _seed_demo(db, user['id'])
                    send_notification(user['id'], f'Welcome to Market Mosaic, {name}! Your dashboard is ready.', channels=('app','whatsapp','sms'))
                session['user_id']=user['id']; session['user_name']=name
                flash(f'Welcome to Market Mosaic, {name}!','success')
                return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError: flash('An account with that email already exists.','error')
    return render_template('signup.html', user=None)

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        with get_db() as db:
            user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if user and check_password_hash(user['password'],password):
            session['user_id']=user['id']; session['user_name']=user['name']
            flash(f'Welcome back, {user["name"]}!','success'); return redirect(url_for('dashboard'))
        flash('Invalid email or password.','error')
    return render_template('login.html', user=None)

@app.route('/logout')
def logout(): session.clear(); flash('Logged out.','success'); return redirect(url_for('home'))

@app.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        email=request.form.get('email','').strip().lower()
        with get_db() as db:
            user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if user:
                token=secrets.token_urlsafe(32); expires=datetime.now()+timedelta(hours=1)
                db.execute('INSERT INTO password_resets (user_id,token,expires_at) VALUES (?,?,?)',(user['id'],token,expires))
                reset_url=url_for('reset_password',token=token,_external=True)
                flash(f'[DEV — wire up Flask-Mail in production] Reset link: {reset_url}','success')
            else: flash('If that email is registered, a reset link has been sent.','success')
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html', user=None)

@app.route('/reset-password/<token>', methods=['GET','POST'])
def reset_password(token):
    with get_db() as db:
        reset=db.execute('SELECT * FROM password_resets WHERE token=? AND used=0 AND expires_at>?',(token,datetime.now())).fetchone()
    valid=reset is not None
    if request.method=='POST' and valid:
        pw=request.form.get('password',''); cf=request.form.get('confirm','')
        if pw!=cf: flash('Passwords do not match.','error')
        elif len(pw)<8: flash('Min 8 characters.','error')
        else:
            with get_db() as db:
                db.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(pw),reset['user_id']))
                db.execute('UPDATE password_resets SET used=1 WHERE id=?',(reset['id'],))
            flash('Password updated! Please log in.','success'); return redirect(url_for('login'))
    return render_template('reset_password.html', user=None, valid=valid, token=token)

# ── DASHBOARD ─────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    user=get_current_user()
    with get_db() as db:
        campaigns=db.execute('SELECT * FROM campaigns WHERE user_id=? ORDER BY created_at DESC LIMIT 5',(user['id'],)).fetchall()
        leads=db.execute('SELECT * FROM leads WHERE user_id=? ORDER BY created_at DESC LIMIT 5',(user['id'],)).fetchall()
        stats={
            'total_campaigns': db.execute('SELECT COUNT(*) FROM campaigns WHERE user_id=?',(user['id'],)).fetchone()[0],
            'active_campaigns':db.execute('SELECT COUNT(*) FROM campaigns WHERE user_id=? AND status="active"',(user['id'],)).fetchone()[0],
            'total_leads':     db.execute('SELECT COUNT(*) FROM leads WHERE user_id=?',(user['id'],)).fetchone()[0],
            'total_spend':     db.execute('SELECT SUM(spent) FROM campaigns WHERE user_id=?',(user['id'],)).fetchone()[0] or 0,
            'total_clicks':    db.execute('SELECT SUM(clicks) FROM campaigns WHERE user_id=?',(user['id'],)).fetchone()[0] or 0,
            'total_impressions':db.execute('SELECT SUM(impressions) FROM campaigns WHERE user_id=?',(user['id'],)).fetchone()[0] or 0,
            'total_conversions':db.execute('SELECT SUM(conversions) FROM campaigns WHERE user_id=?',(user['id'],)).fetchone()[0] or 0,
        }
    return render_template('dashboard.html', user=user, campaigns=campaigns, leads=leads,
                           stats=stats, now_hour=datetime.now().hour, unread=unread(user['id']))

# ── CAMPAIGNS ─────────────────────────────────────────────
@app.route('/dashboard/campaigns')
@login_required
def campaigns():
    user=get_current_user(); sf=request.args.get('status','')
    with get_db() as db:
        q='SELECT * FROM campaigns WHERE user_id=?'; p=[user['id']]
        if sf: q+=' AND status=?'; p.append(sf)
        rows=db.execute(q+' ORDER BY created_at DESC',p).fetchall()
    return render_template('campaigns.html', user=user, campaigns=rows, status_filter=sf, unread=unread(user['id']))

@app.route('/dashboard/campaigns/new', methods=['GET','POST'])
@login_required
def new_campaign():
    user=get_current_user()
    if request.method=='POST':
        name=request.form.get('name','').strip(); channel=request.form.get('channel','')
        budget=float(request.form.get('budget',0) or 0); status=request.form.get('status','draft')
        notes=request.form.get('notes','').strip()
        if name and channel:
            with get_db() as db:
                db.execute('INSERT INTO campaigns (user_id,name,channel,budget,status,notes) VALUES (?,?,?,?,?,?)',
                           (user['id'],name,channel,budget,status,notes))
            send_notification(user['id'], f'Campaign "{name}" created successfully.', channels=('app','whatsapp','sms'))
            flash('Campaign created!','success'); return redirect(url_for('campaigns'))
        flash('Name and channel required.','error')
    return render_template('new_campaign.html', user=user, unread=unread(user['id']))

@app.route('/dashboard/campaigns/<int:cid>/edit', methods=['GET','POST'])
@login_required
def edit_campaign(cid):
    user=get_current_user()
    with get_db() as db:
        c=db.execute('SELECT * FROM campaigns WHERE id=? AND user_id=?',(cid,user['id'])).fetchone()
    if not c: flash('Not found.','error'); return redirect(url_for('campaigns'))
    if request.method=='POST':
        with get_db() as db:
            db.execute('''UPDATE campaigns SET name=?,channel=?,budget=?,spent=?,impressions=?,
                          clicks=?,conversions=?,status=?,notes=? WHERE id=? AND user_id=?''',
                       (request.form.get('name'),request.form.get('channel'),
                        float(request.form.get('budget',0) or 0),float(request.form.get('spent',0) or 0),
                        int(request.form.get('impressions',0) or 0),int(request.form.get('clicks',0) or 0),
                        int(request.form.get('conversions',0) or 0),request.form.get('status'),
                        request.form.get('notes',''),cid,user['id']))
        flash('Campaign updated!','success'); return redirect(url_for('campaigns'))
    return render_template('edit_campaign.html', user=user, campaign=c, unread=unread(user['id']))

@app.route('/dashboard/campaigns/<int:cid>/delete', methods=['POST'])
@login_required
def delete_campaign(cid):
    user=get_current_user()
    with get_db() as db: db.execute('DELETE FROM campaigns WHERE id=? AND user_id=?',(cid,user['id']))
    flash('Campaign deleted.','success'); return redirect(url_for('campaigns'))

@app.route('/dashboard/campaigns/export')
@login_required
def export_campaigns():
    user=get_current_user()
    with get_db() as db:
        rows=db.execute('SELECT * FROM campaigns WHERE user_id=? ORDER BY created_at DESC',(user['id'],)).fetchall()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(['ID','Name','Channel','Status','Budget','Spent','Impressions','Clicks','Conversions','CTR%','Created'])
    for r in rows:
        ctr=f"{r['clicks']/r['impressions']*100:.2f}" if r['impressions']>0 else '0'
        w.writerow([r['id'],r['name'],r['channel'],r['status'],r['budget'],r['spent'],
                    r['impressions'],r['clicks'],r['conversions'],ctr,r['created_at'][:10]])
    out.seek(0)
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':'attachment;filename=campaigns_export.csv'})

# ── LEADS ─────────────────────────────────────────────────
@app.route('/dashboard/leads')
@login_required
def leads():
    user=get_current_user(); sf=request.args.get('status',''); search=request.args.get('q','').strip()
    with get_db() as db:
        q='SELECT * FROM leads WHERE user_id=?'; p=[user['id']]
        if sf: q+=' AND status=?'; p.append(sf)
        if search:
            q+=' AND (name LIKE ? OR email LIKE ? OR company LIKE ?)'
            p+=[f'%{search}%',f'%{search}%',f'%{search}%']
        rows=db.execute(q+' ORDER BY created_at DESC',p).fetchall()
    return render_template('leads.html', user=user, leads=rows, status_filter=sf, search=search, unread=unread(user['id']))

@app.route('/dashboard/leads/new', methods=['GET','POST'])
@login_required
def new_lead():
    user=get_current_user()
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip()
        company=request.form.get('company','').strip(); phone=request.form.get('phone','').strip()
        source=request.form.get('source','organic'); status=request.form.get('status','new')
        notes=request.form.get('notes','').strip()
        if name and email:
            with get_db() as db:
                db.execute('INSERT INTO leads (user_id,name,email,company,phone,source,status,notes) VALUES (?,?,?,?,?,?,?,?)',
                           (user['id'],name,email,company,phone,source,status,notes))
            send_notification(user['id'], f'New lead "{name}" added to your pipeline.', channels=('app','whatsapp','sms'))
            flash('Lead added!','success'); return redirect(url_for('leads'))
        flash('Name and email required.','error')
    return render_template('new_lead.html', user=user, unread=unread(user['id']))

@app.route('/dashboard/leads/<int:lid>/edit', methods=['GET','POST'])
@login_required
def edit_lead(lid):
    user=get_current_user()
    with get_db() as db:
        lead=db.execute('SELECT * FROM leads WHERE id=? AND user_id=?',(lid,user['id'])).fetchone()
    if not lead: flash('Not found.','error'); return redirect(url_for('leads'))
    if request.method=='POST':
        with get_db() as db:
            db.execute('UPDATE leads SET name=?,email=?,company=?,phone=?,source=?,status=?,notes=? WHERE id=? AND user_id=?',
                       (request.form.get('name'),request.form.get('email'),request.form.get('company'),
                        request.form.get('phone'),request.form.get('source'),request.form.get('status'),
                        request.form.get('notes',''),lid,user['id']))
        flash('Lead updated!','success'); return redirect(url_for('leads'))
    return render_template('edit_lead.html', user=user, lead=lead, unread=unread(user['id']))

@app.route('/dashboard/leads/<int:lid>/delete', methods=['POST'])
@login_required
def delete_lead(lid):
    user=get_current_user()
    with get_db() as db: db.execute('DELETE FROM leads WHERE id=? AND user_id=?',(lid,user['id']))
    flash('Lead deleted.','success'); return redirect(url_for('leads'))

@app.route('/dashboard/leads/export')
@login_required
def export_leads():
    user=get_current_user()
    with get_db() as db:
        rows=db.execute('SELECT * FROM leads WHERE user_id=? ORDER BY created_at DESC',(user['id'],)).fetchall()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(['ID','Name','Email','Company','Phone','Source','Status','Notes','Created'])
    for r in rows:
        w.writerow([r['id'],r['name'],r['email'],r['company'] or '',r['phone'] or '',
                    r['source'],r['status'],r['notes'] or '',r['created_at'][:10]])
    out.seek(0)
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':'attachment;filename=leads_export.csv'})

# ── ANALYTICS ─────────────────────────────────────────────
@app.route('/dashboard/analytics')
@login_required
def analytics():
    user=get_current_user()
    with get_db() as db:
        camp=db.execute('SELECT * FROM campaigns WHERE user_id=?',(user['id'],)).fetchall()
        lsrc=db.execute('SELECT source,COUNT(*) as cnt FROM leads WHERE user_id=? GROUP BY source',(user['id'],)).fetchall()
        lst=db.execute('SELECT status,COUNT(*) as cnt FROM leads WHERE user_id=? GROUP BY status',(user['id'],)).fetchall()
    chart_data={
        'labels':[c['name'] for c in camp],'clicks':[c['clicks'] for c in camp],
        'impressions':[c['impressions'] for c in camp],'spent':[c['spent'] for c in camp],
        'conversions':[c['conversions'] for c in camp],
        'lead_sources':[r['source'] for r in lsrc],'lead_source_counts':[r['cnt'] for r in lsrc],
        'lead_statuses':[r['status'] for r in lst],'lead_status_counts':[r['cnt'] for r in lst],
    }
    return render_template('analytics.html', user=user, chart_data=json.dumps(chart_data), unread=unread(user['id']))

# ── NOTIFICATIONS ─────────────────────────────────────────
@app.route('/dashboard/notifications')
@login_required
def notifications():
    user=get_current_user()
    with get_db() as db:
        notifs=db.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC',(user['id'],)).fetchall()
        db.execute('UPDATE notifications SET read=1 WHERE user_id=?',(user['id'],))
    return render_template('notifications.html', user=user, notifs=notifs, unread=0)

# ── SETTINGS ──────────────────────────────────────────────
@app.route('/dashboard/settings', methods=['GET','POST'])
@login_required
def settings():
    user=get_current_user()
    if request.method=='POST':
        action=request.form.get('action','profile')
        if action=='profile':
            name=request.form.get('name','').strip(); company=request.form.get('company','').strip()
            if name and company:
                with get_db() as db: db.execute('UPDATE users SET name=?,company=? WHERE id=?',(name,company,user['id']))
                session['user_name']=name; flash('Profile updated!','success')
        elif action=='password':
            curr=request.form.get('current_password',''); npw=request.form.get('new_password',''); conf=request.form.get('confirm_password','')
            if not check_password_hash(user['password'],curr): flash('Current password incorrect.','error')
            elif npw!=conf: flash('New passwords do not match.','error')
            elif len(npw)<8: flash('Min 8 characters.','error')
            else:
                with get_db() as db: db.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(npw),user['id']))
                flash('Password changed!','success')
        elif action=='regenerate_key':
            nk='mm_'+secrets.token_hex(24)
            with get_db() as db: db.execute('UPDATE users SET api_key=? WHERE id=?',(nk,user['id']))
            flash('API key regenerated.','success')
        return redirect(url_for('settings'))
    user=get_current_user()
    return render_template('settings.html', user=user, unread=unread(user['id']))

# ── ADMIN ─────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin():
    with get_db() as db:
        users=db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
        stats={'total_users':db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
               'total_campaigns':db.execute('SELECT COUNT(*) FROM campaigns').fetchone()[0],
               'total_leads':db.execute('SELECT COUNT(*) FROM leads').fetchone()[0]}
    return render_template('admin.html', user=get_current_user(), users=users, stats=stats)

@app.route('/admin/users/<int:uid>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(uid):
    with get_db() as db:
        u=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if u and u['id']!=session['user_id']:
            db.execute('UPDATE users SET is_admin=? WHERE id=?',(0 if u['is_admin'] else 1,uid))
    flash('User updated.','success'); return redirect(url_for('admin'))

@app.route('/admin/users/<int:uid>/delete', methods=['POST'])
@admin_required
def admin_delete_user(uid):
    if uid==session['user_id']: flash("You can't delete yourself.",'error'); return redirect(url_for('admin'))
    with get_db() as db:
        for t in ['campaigns','leads','notifications','password_resets']:
            db.execute(f'DELETE FROM {t} WHERE user_id=?',(uid,))
        db.execute('DELETE FROM users WHERE id=?',(uid,))
    flash('User deleted.','success'); return redirect(url_for('admin'))

# ── REST API ──────────────────────────────────────────────
@app.route('/api/v1/campaigns')
def api_campaigns():
    u=api_auth()
    if not u: return jsonify({'error':'Unauthorized'}),401
    with get_db() as db: rows=db.execute('SELECT * FROM campaigns WHERE user_id=?',(u['id'],)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/v1/leads')
def api_leads():
    u=api_auth()
    if not u: return jsonify({'error':'Unauthorized'}),401
    with get_db() as db: rows=db.execute('SELECT * FROM leads WHERE user_id=?',(u['id'],)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/v1/stats')
def api_stats():
    u=api_auth()
    if not u: return jsonify({'error':'Unauthorized'}),401
    with get_db() as db:
        return jsonify({'campaigns':db.execute('SELECT COUNT(*) FROM campaigns WHERE user_id=?',(u['id'],)).fetchone()[0],
                        'leads':db.execute('SELECT COUNT(*) FROM leads WHERE user_id=?',(u['id'],)).fetchone()[0],
                        'spend':db.execute('SELECT SUM(spent) FROM campaigns WHERE user_id=?',(u['id'],)).fetchone()[0] or 0,
                        'clicks':db.execute('SELECT SUM(clicks) FROM campaigns WHERE user_id=?',(u['id'],)).fetchone()[0] or 0})

# ── ERRORS ────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e): return render_template('404.html', user=get_current_user()), 404

@app.errorhandler(500)
def server_error(e): return render_template('500.html', user=get_current_user()), 500

# ── SEED ──────────────────────────────────────────────────
def _seed_demo(db, uid):
    db.executemany('INSERT INTO campaigns (user_id,name,channel,status,budget,spent,impressions,clicks,conversions) VALUES (?,?,?,?,?,?,?,?,?)',
        [(uid,'Q2 Brand Awareness','Social Media','active',50000,31200,420000,8400,312),
         (uid,'Google Search — India','Search','active',30000,18750,180000,5400,189),
         (uid,'Email Nurture Series','Email','paused',8000,4200,22000,3100,87),
         (uid,'LinkedIn B2B Push','LinkedIn','draft',20000,0,0,0,0)])
    db.executemany('INSERT INTO leads (user_id,name,email,company,source,status) VALUES (?,?,?,?,?,?)',
        [(uid,'Priya Sharma','priya@techcorp.in','TechCorp India','LinkedIn','qualified'),
         (uid,'Rohan Mehta','rohan@startup.io','LaunchPad','Organic','new'),
         (uid,'Ananya Iyer','ananya@brandco.com','BrandCo','Referral','contacted'),
         (uid,'Vikram Das','vikram@retail.in','Retail Plus','Google','new'),
         (uid,'Sunita Rao','sunita@fmcg.co','FMCG Pvt Ltd','Email','qualified')])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

# ── REPORTS ───────────────────────────────────────────────
@app.route('/dashboard/reports')
@login_required
def reports():
    user = get_current_user()
    with get_db() as db:
        campaigns = db.execute('SELECT * FROM campaigns WHERE user_id=? ORDER BY spent DESC', (user['id'],)).fetchall()
        lead_by_status = db.execute('SELECT status, COUNT(*) as cnt FROM leads WHERE user_id=? GROUP BY status', (user['id'],)).fetchall()
        lead_by_source = db.execute('SELECT source, COUNT(*) as cnt FROM leads WHERE user_id=? GROUP BY source ORDER BY cnt DESC', (user['id'],)).fetchall()
        channel_spend  = db.execute('SELECT channel, SUM(spent) as spend FROM campaigns WHERE user_id=? GROUP BY channel ORDER BY spend DESC', (user['id'],)).fetchall()
        qualified_leads = db.execute('SELECT COUNT(*) FROM leads WHERE user_id=? AND status="qualified"', (user['id'],)).fetchone()[0]
        stats = {
            'total_campaigns':  db.execute('SELECT COUNT(*) FROM campaigns WHERE user_id=?', (user['id'],)).fetchone()[0],
            'active_campaigns': db.execute('SELECT COUNT(*) FROM campaigns WHERE user_id=? AND status="active"', (user['id'],)).fetchone()[0],
            'total_leads':      db.execute('SELECT COUNT(*) FROM leads WHERE user_id=?', (user['id'],)).fetchone()[0],
            'qualified_leads':  qualified_leads,
            'total_spend':      db.execute('SELECT SUM(spent) FROM campaigns WHERE user_id=?', (user['id'],)).fetchone()[0] or 0,
            'total_clicks':     db.execute('SELECT SUM(clicks) FROM campaigns WHERE user_id=?', (user['id'],)).fetchone()[0] or 0,
            'total_impressions':db.execute('SELECT SUM(impressions) FROM campaigns WHERE user_id=?', (user['id'],)).fetchone()[0] or 0,
            'total_conversions':db.execute('SELECT SUM(conversions) FROM campaigns WHERE user_id=?', (user['id'],)).fetchone()[0] or 0,
        }
    return render_template('reports.html', user=user, campaigns=campaigns, stats=stats,
                           lead_by_status=lead_by_status, lead_by_source=lead_by_source,
                           channel_spend=channel_spend, now=datetime.now().strftime('%d %b %Y'),
                           unread=unread(user['id']))

# ── PROPOSALS ─────────────────────────────────────────────
@app.route('/dashboard/proposals')
@login_required
def proposals():
    user = get_current_user()
    return render_template('proposals.html', user=user, now=datetime.now().strftime('%d %b %Y'),
                           unread=unread(user['id']))

# ── EMAIL TEMPLATES ───────────────────────────────────────
EMAIL_TEMPLATES = [
    {
        'name': 'New Client Welcome',
        'tag': 'Onboarding',
        'subject': 'Welcome to Market Mosaic — Next Steps',
        'body': """Hi [Client Name],

Welcome aboard! We're thrilled to be partnering with [Company Name] on this journey.

Here's what happens next:

1. Kick-off call — We'll schedule a 60-minute session to align on goals, timelines, and key contacts.
2. Discovery questionnaire — You'll receive a short form to help us understand your brand, audience, and competitors.
3. Strategy draft — Within 5 working days of our kick-off, we'll share an initial strategy for your review.

In the meantime, feel free to reach out with any questions at hello@marketmosaic.in.

Looking forward to building something great together.

Warm regards,
[Your Name]
Market Mosaic"""
    },
    {
        'name': 'Monthly Report',
        'tag': 'Reporting',
        'subject': '[Company Name] — Marketing Report — [Month Year]',
        'body': """Hi [Client Name],

Please find below your marketing performance summary for [Month Year].

CAMPAIGN HIGHLIGHTS
-------------------
• Impressions: [X]
• Clicks: [X] (CTR: [X]%)
• Conversions: [X]
• Total Spend: Rs [X]
• Cost per Conversion: Rs [X]

WHAT WORKED WELL
• [Insight 1]
• [Insight 2]

FOCUS FOR NEXT MONTH
• [Action 1]
• [Action 2]

The full report with breakdowns is attached. Happy to walk through it on a call — just let me know.

Best,
[Your Name]
Market Mosaic"""
    },
    {
        'name': 'Proposal Follow-Up',
        'tag': 'Sales',
        'subject': 'Following up — Marketing Proposal for [Company Name]',
        'body': """Hi [Client Name],

I wanted to follow up on the proposal we shared on [Date].

We've put together what we believe is a strong approach for [Company Name] — one that balances quick wins with a longer-term brand-building strategy.

A few things I'd love to get your perspective on:
• Does the scope feel right for your current priorities?
• Are there any services you'd like to adjust or swap out?
• Do you have any questions about the investment?

I'm happy to jump on a 20-minute call to address any questions. You can book a time here: [Calendar Link]

Looking forward to hearing from you.

Best,
[Your Name]
Market Mosaic"""
    },
    {
        'name': 'Campaign Launch',
        'tag': 'Campaigns',
        'subject': '[Campaign Name] Is Live — Here\'s What to Expect',
        'body': """Hi [Client Name],

Great news — [Campaign Name] is officially live!

CAMPAIGN DETAILS
----------------
• Channel: [Channel]
• Start Date: [Date]
• Budget: Rs [Amount]
• Goal: [Objective]

WHAT TO EXPECT IN THE FIRST 2 WEEKS
The first two weeks are primarily a learning phase. Algorithms need data to optimise, and we typically see performance improve steadily after the first 7–10 days.

We'll share a mid-point check-in in 2 weeks with early data and any optimisation notes.

In the meantime, if you have any questions or feedback, don't hesitate to reach out.

Exciting times ahead!

Best,
[Your Name]
Market Mosaic"""
    },
    {
        'name': 'Invoice / Payment Request',
        'tag': 'Finance',
        'subject': 'Invoice #[Number] — Market Mosaic — [Month Year]',
        'body': """Hi [Client Name],

Please find Invoice #[Number] for services rendered in [Month Year].

INVOICE SUMMARY
---------------
• Service: [Description]
• Period: [Start Date] to [End Date]
• Amount: Rs [Total]
• Due Date: [Due Date]

Payment can be made to:
Account Name: Market Mosaic
Account No: [XXXX]
IFSC: [XXXX]
UPI: [ID]

Please use Invoice #[Number] as the payment reference.

If you have any questions, please don't hesitate to get in touch.

Thank you for your continued partnership.

Best,
[Your Name]
Market Mosaic"""
    },
    {
        'name': 'Feedback Request',
        'tag': 'Retention',
        'subject': 'A Quick Note from Market Mosaic',
        'body': """Hi [Client Name],

It's been [X months] since we started working together, and I wanted to take a moment to check in.

We're always looking to improve, and your feedback matters to us. I have two quick questions:

1. On a scale of 1–10, how satisfied are you with our work so far?
2. Is there anything we could be doing better or differently?

Feel free to reply directly to this email — even a few words would be incredibly helpful.

Thank you for taking the time. We genuinely value this partnership.

Warm regards,
[Your Name]
Market Mosaic"""
    },
]

@app.route('/dashboard/email-templates')
@login_required
def email_templates():
    user = get_current_user()
    return render_template('email_templates.html', user=user, templates=EMAIL_TEMPLATES,
                           templates_json=json.dumps(EMAIL_TEMPLATES), unread=unread(user['id']))

# ════════════════════════════════════════════════════════
# PAYMENTS — Razorpay (UPI + Cards + Netbanking)
# ════════════════════════════════════════════════════════
# pip install razorpay
# Set env vars: RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
# Sign up free at razorpay.com — no monthly fee, 2% per txn

import hmac, hashlib

RAZORPAY_KEY_ID     = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')

PLANS = {
    'starter': {'name': 'Starter', 'price': 0,    'amount_paise': 0,      'plan_id': 'free'},
    'growth':  {'name': 'Growth',  'price': 2999,  'amount_paise': 299900, 'plan_id': 'growth'},
    'agency':  {'name': 'Agency',  'price': 7999,  'amount_paise': 799900, 'plan_id': 'agency'},
}

def razorpay_client():
    try:
        import razorpay
        return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    except ImportError:
        return None

@app.route('/dashboard/billing')
@login_required
def billing():
    user = get_current_user()
    with get_db() as db:
        payments = db.execute(
            'SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC', (user['id'],)
        ).fetchall()
    return render_template('billing.html', user=user, plans=PLANS,
                           payments=payments, razorpay_key=RAZORPAY_KEY_ID,
                           unread=unread(user['id']))

@app.route('/billing/create-order', methods=['POST'])
@login_required
def create_order():
    user = get_current_user()
    plan_id = request.form.get('plan_id')
    plan = PLANS.get(plan_id)
    if not plan or plan['amount_paise'] == 0:
        flash('Invalid plan.', 'error')
        return redirect(url_for('billing'))

    client = razorpay_client()
    if not client:
        flash('Payment system not configured. Install razorpay: pip install razorpay', 'error')
        return redirect(url_for('billing'))

    order = client.order.create({
        'amount':   plan['amount_paise'],
        'currency': 'INR',
        'notes':    {'user_id': str(user['id']), 'plan': plan_id}
    })

    return render_template('checkout.html', user=user,
                           order=order, plan=plan,
                           razorpay_key=RAZORPAY_KEY_ID,
                           unread=unread(user['id']))

@app.route('/billing/verify', methods=['POST'])
@login_required
def verify_payment():
    user = get_current_user()
    data = request.form

    razorpay_order_id   = data.get('razorpay_order_id', '')
    razorpay_payment_id = data.get('razorpay_payment_id', '')
    razorpay_signature  = data.get('razorpay_signature', '')
    plan_id             = data.get('plan_id', '')

    # Verify signature
    msg     = f'{razorpay_order_id}|{razorpay_payment_id}'.encode()
    secret  = RAZORPAY_KEY_SECRET.encode()
    gen_sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()

    if gen_sig == razorpay_signature:
        plan = PLANS.get(plan_id, {})
        with get_db() as db:
            db.execute('UPDATE users SET plan=? WHERE id=?', (plan_id, user['id']))
            db.execute(
                'INSERT INTO payments (user_id,order_id,payment_id,plan,amount,status) VALUES (?,?,?,?,?,?)',
                (user['id'], razorpay_order_id, razorpay_payment_id,
                 plan_id, plan.get('price', 0), 'success')
            )
        add_notification(user['id'], f'Payment successful! You are now on the {plan.get("name","")} plan.')
        _send_whatsapp(user['id'], f'✅ Payment confirmed! Your Market Mosaic account has been upgraded to the {plan.get("name","")} plan.')
        _send_sms(user['id'], f'Payment confirmed. Market Mosaic account upgraded to {plan.get("name","")} plan.')
        flash(f'Payment successful! You are now on the {plan.get("name","")} plan.', 'success')
    else:
        with get_db() as db:
            db.execute(
                'INSERT INTO payments (user_id,order_id,payment_id,plan,amount,status) VALUES (?,?,?,?,?,?)',
                (user['id'], razorpay_order_id, razorpay_payment_id, plan_id, 0, 'failed')
            )
        flash('Payment verification failed. Please contact support.', 'error')

    return redirect(url_for('billing'))

@app.route('/billing/webhook', methods=['POST'])
def razorpay_webhook():
    """Razorpay webhook endpoint — set this URL in Razorpay dashboard"""
    webhook_secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
    payload        = request.get_data()
    signature      = request.headers.get('X-Razorpay-Signature', '')

    if webhook_secret:
        gen = hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        if gen != signature:
            return jsonify({'error': 'Invalid signature'}), 400

    event = request.json
    if event.get('event') == 'payment.captured':
        payment = event['payload']['payment']['entity']
        notes   = payment.get('notes', {})
        user_id = notes.get('user_id')
        plan_id = notes.get('plan')
        if user_id and plan_id:
            with get_db() as db:
                db.execute('UPDATE users SET plan=? WHERE id=?', (plan_id, user_id))
    return jsonify({'status': 'ok'})


# ════════════════════════════════════════════════════════
# NOTIFICATIONS — WhatsApp (Twilio) + SMS (Fast2SMS)
# ════════════════════════════════════════════════════════
# WhatsApp: pip install twilio — free sandbox at twilio.com
# SMS:      Free at fast2sms.com (Indian numbers, no registration needed for dev)
# Set env vars: TWILIO_SID, TWILIO_TOKEN, TWILIO_WHATSAPP_FROM
#               FAST2SMS_KEY

TWILIO_SID            = os.environ.get('TWILIO_SID', '')
TWILIO_TOKEN          = os.environ.get('TWILIO_TOKEN', '')
TWILIO_WHATSAPP_FROM  = os.environ.get('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')  # Twilio sandbox
FAST2SMS_KEY          = os.environ.get('FAST2SMS_KEY', '')

def _get_user_phone(user_id):
    """Fetch a user's phone number from the DB"""
    with get_db() as db:
        row = db.execute('SELECT phone FROM users WHERE id=?', (user_id,)).fetchone()
        return row['phone'] if row and row['phone'] else None

def _send_whatsapp(user_id, message):
    """Send a WhatsApp message via Twilio. Silently skips if not configured or user opted out."""
    if not all([TWILIO_SID, TWILIO_TOKEN]):
        return
    with get_db() as db:
        u = db.execute('SELECT phone, notif_whatsapp FROM users WHERE id=?', (user_id,)).fetchone()
        if not u or not u['notif_whatsapp'] or not u['phone']:
            return
    phone = u['phone']
    try:
        try:
            from twilio.rest import Client
        except ImportError:
            return
        to_wa = f'whatsapp:{phone}' if not phone.startswith('whatsapp:') else phone
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(from_=TWILIO_WHATSAPP_FROM, to=to_wa, body=message)
    except Exception as e:
        app.logger.warning(f'WhatsApp send failed: {e}')

def _send_sms(user_id, message):
    """Send SMS via Fast2SMS (India). Silently skips if not configured or user opted out."""
    if not FAST2SMS_KEY:
        return
    with get_db() as db:
        u = db.execute('SELECT phone, notif_sms FROM users WHERE id=?', (user_id,)).fetchone()
        if not u or not u['notif_sms'] or not u['phone']:
            return
    phone = u['phone']
    # Strip +91 or 0 prefix for Fast2SMS
    number = phone.strip().lstrip('+').lstrip('91').lstrip('0')
    if len(number) != 10:
        return
    try:
        import urllib.request, urllib.parse
        payload = urllib.parse.urlencode({
            'sender_id': 'FSTSMS',
            'message':   message,
            'language':  'english',
            'route':     'q',
            'numbers':   number,
        }).encode()
        req = urllib.request.Request(
            'https://www.fast2sms.com/dev/bulkV2',
            data=payload,
            headers={'authorization': FAST2SMS_KEY, 'Content-Type': 'application/x-www-form-urlencoded'},
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        app.logger.warning(f'SMS send failed: {e}')

def send_notification(user_id, message, channels=('app', 'whatsapp', 'sms')):
    """Unified notification dispatcher — send to any combination of channels."""
    if 'app' in channels:
        add_notification(user_id, message)
    if 'whatsapp' in channels:
        _send_whatsapp(user_id, f'Market Mosaic: {message}')
    if 'sms' in channels:
        _send_sms(user_id, f'Market Mosaic: {message}')

# ── NOTIFICATION SETTINGS (user preferences) ─────────────
@app.route('/dashboard/notification-settings', methods=['GET', 'POST'])
@login_required
def notification_settings():
    user = get_current_user()
    if request.method == 'POST':
        phone         = request.form.get('phone', '').strip()
        notif_app     = 1 if request.form.get('notif_app') else 0
        notif_whatsapp= 1 if request.form.get('notif_whatsapp') else 0
        notif_sms     = 1 if request.form.get('notif_sms') else 0
        with get_db() as db:
            db.execute(
                'UPDATE users SET phone=?, notif_app=?, notif_whatsapp=?, notif_sms=? WHERE id=?',
                (phone, notif_app, notif_whatsapp, notif_sms, user['id'])
            )
        # Send test messages if requested
        if request.form.get('test_whatsapp') and phone:
            _send_whatsapp(user['id'], '👋 Test message from Market Mosaic! WhatsApp notifications are working.')
        if request.form.get('test_sms') and phone:
            _send_sms(user['id'], 'Test message from Market Mosaic. SMS notifications working.')
        flash('Notification preferences saved!', 'success')
        return redirect(url_for('notification_settings'))
    user = get_current_user()
    return render_template('notification_settings.html', user=user,
                           twilio_configured=bool(TWILIO_SID),
                           fast2sms_configured=bool(FAST2SMS_KEY),
                           unread=unread(user['id']))

# ── MANUAL NOTIFICATION SEND (admin/testing) ──────────────
@app.route('/dashboard/send-notification', methods=['POST'])
@login_required
def send_test_notification():
    user = get_current_user()
    msg      = request.form.get('message', '').strip()
    channels = request.form.getlist('channels')
    if msg:
        send_notification(user['id'], msg, channels=channels)
        flash(f'Notification sent via: {", ".join(channels) if channels else "none"}', 'success')
    return redirect(url_for('notification_settings'))
