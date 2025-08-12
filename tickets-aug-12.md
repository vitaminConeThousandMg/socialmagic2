# SocialMagic Development Tickets - Updated with Code References

## 🚨 CRITICAL PRIORITY (Application Breaking)

### **TICKET-001: Fix Duplicate Code in utils.py**
**Status:** BROKEN - File contains duplicate content
**Issue:** Entire file content is duplicated, causing syntax errors

**Affected Files:**
- `utils.py` (Lines 1-89 duplicated at lines 90-178)

**Action Items:**
- Remove duplicate code starting at line 90
- Keep only one version of each function
- Test email sending functionality

**Code Reference:**
```python
# Line 1-89: First version of functions
def send_verification_email(user):
    """Send email verification"""
    ...

# Line 90-178: DUPLICATE - Remove this entire section
def send_verification_email(user):  # Duplicate starts here
    """Send email verification"""
    ...
```

---

### **TICKET-002: Implement Missing Core Routes**
**Status:** BROKEN - Templates exist but routes missing
**Issue:** Multiple navigation links lead to 404 errors

**Missing Routes in `main.py`:**
1. **`/media_library`** - Referenced in:
   - `templates/base.html` (Line 64)
   - `templates/dashboard.html` (Line 78)
   
2. **`/queue`** - Referenced in:
   - `templates/base.html` (Line 73)
   - Template exists at `templates/queue.html`

3. **`/upload` POST** - Referenced in:
   - `templates/upload.html` (Line 23)
   - `templates/base.html` (Line 58)

**Action Items:**
```python
# Add to main.py after line 48

@main_bp.route('/media_library')
@login_required
def media_library():
    page = request.args.get('page', 1, type=int)
    media = Post.query.filter_by(user_id=current_user.id)\
        .paginate(page=page, per_page=20, error_out=False)
    return render_template('media_library.html', media=media)

@main_bp.route('/queue')
@login_required
def queue():
    processing_posts = Post.query.filter_by(
        user_id=current_user.id,
        status=PostStatus.PENDING
    ).all()
    scheduled_posts = Post.query.filter_by(
        user_id=current_user.id,
        status=PostStatus.SCHEDULED
    ).all()
    return render_template('queue.html', 
                         processing_posts=processing_posts,
                         scheduled_posts=scheduled_posts)

@main_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    # Implementation needed
    pass
```

---

### **TICKET-003: Create Missing posts.html Template**
**Status:** MISSING - Core template referenced but doesn't exist
**Issue:** Post management page crashes with template not found

**References:**
- `main.py` (Line 76): `return render_template('posts.html', ...)`
- Called from dashboard for post review workflow

**Action Items:**
- Create `templates/posts.html` with approval UI
- Include JavaScript for approve/reject actions
- Add media preview functionality

**Required Template Structure:**
```html
<!-- templates/posts.html -->
{% extends "base.html" %}
{% block page_title %}Review Posts{% endblock %}
{% block content %}
<!-- Add post cards with approve/reject buttons -->
<!-- Include AJAX calls to /api/posts/{id}/approve and /reject -->
{% endblock %}
```

---

## 🔴 HIGH PRIORITY

### **TICKET-004: Fix Missing Model Definitions**
**Status:** BROKEN - Referenced models don't exist
**Issue:** Code references undefined models causing import errors

**Missing Models:**
1. **`ImageReference`** - Referenced in:
   - `webhooks.py` (Lines 18, 39, 61, 76)
   - `utils.py` (Lines 86, 174)

2. **`WebhookEvent`** - Referenced in:
   - `tasks/monitoring.py` (Lines 7, 82, 156)

**Action Items - Add to `models.py`:**
```python
# Add after line 256 in models.py

class ImageReference(db.Model):
    __tablename__ = 'image_references'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    n8n_media_id = db.Column(db.String(100))
    original_filename = db.Column(db.String(255))
    file_type = db.Column(db.String(50))
    status = db.Column(db.String(50), default='pending')
    posted = db.Column(db.Boolean, default=False)
    posted_at = db.Column(db.DateTime)
    instagram_post_id = db.Column(db.String(100))
    instagram_url = db.Column(db.String(500))
    facebook_post_id = db.Column(db.String(100))
    caption = db.Column(db.Text)
    hashtags = db.Column(db.JSON)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

class WebhookEvent(db.Model):
    __tablename__ = 'webhook_events'
    
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50))
    payload = db.Column(db.JSON)
    processed = db.Column(db.Boolean, default=False)
    processed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

---

### **TICKET-005: Complete File Upload Implementation**
**Status:** INCOMPLETE - Frontend exists, backend missing
**Issue:** Upload form submits but no handler exists

**Affected Files:**
- `templates/upload.html` (Line 23): Form posts to `/upload`
- `main.py`: Missing POST handler
- `forms.py`: Missing `FileUploadForm`

**Action Items:**
1. Add to `forms.py` (after line 53):
```python
class FileUploadForm(FlaskForm):
    files = FileField('Upload Files', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'mp4'], 'Images and videos only!')
    ])
    submit = SubmitField('Upload')
```

2. Implement upload route in `main.py`:
```python
@main_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = FileUploadForm()
    if form.validate_on_submit():
        # Process uploaded files
        # Save to S3 using storage_service
        # Create Post records
        pass
    return render_template('upload.html', form=form)
```

---

### **TICKET-006: Fix Media Display in Templates**
**Status:** BROKEN - Shows placeholder emojis instead of images
**Issue:** Media URLs exist but not rendered

**Affected Templates:**
- `templates/media_library.html` (Lines 19-26): Shows 📷 emoji
- `templates/dashboard.html` (Lines 91-92): Shows 📷 emoji
- `templates/queue.html` (Lines 15, 48): Shows 📷 emoji

**Fix Required:**
```html
<!-- Replace in media_library.html line 20-22 -->
<!-- FROM: -->
<div style="width: 100%; height: 100%; background: var(--light-gray); ...">
    {% if item.file_type and item.file_type.startswith('image/') %}📷{% else %}📹{% endif %}
</div>

<!-- TO: -->
{% if item.media_url %}
    {% if item.media_type.value == 'image' %}
        <img src="{{ item.media_url }}" alt="{{ item.original_filename }}" style="width: 100%; height: 100%; object-fit: cover;">
    {% else %}
        <video src="{{ item.media_url }}" style="width: 100%; height: 100%; object-fit: cover;" controls></video>
    {% endif %}
{% else %}
    <div style="width: 100%; height: 100%; background: var(--light-gray); ...">
        {% if item.media_type.value == 'image' %}📷{% else %}📹{% endif %}
    </div>
{% endif %}
```

---

### **TICKET-007: Fix Dashboard Stats Calculation**
**Status:** BROKEN - Undefined variables in template
**Issue:** Dashboard references undefined stats

**Affected Files:**
- `templates/dashboard.html` (Line 64): References `stats.total_media`
- `main.py` (Line 36): Stats dict missing `total_media` key

**Fix in `main.py` (Line 36):**
```python
# Add to stats dictionary
stats = {
    'total_posts': total_posts,
    'total_reach': total_reach,
    'scheduled': scheduled_posts,
    'total_generated': total_generated,
    'pending': pending_posts,
    'total_media': Post.query.filter_by(user_id=current_user.id).count(),  # ADD THIS
    'processing': Post.query.filter_by(user_id=current_user.id, status=PostStatus.PENDING).count()  # ADD THIS
}
```

---

## 🟡 MEDIUM PRIORITY

### **TICKET-008: Fix Duplicate AI Service Method**
**Status:** DUPLICATE CODE - Method defined twice
**Issue:** `generate_campaign_prompts` defined twice in same file

**Affected File:**
- `services/ai_service.py`:
  - First definition: Lines 247-337
  - Duplicate definition: Lines 400-490 (REMOVE)

**Action Items:**
- Delete lines 400-490 (duplicate method)
- Keep first implementation (more complete)

---

### **TICKET-009: Implement Campaign UI JavaScript**
**Status:** STUB - Empty function implementations
**Issue:** Campaign buttons don't work

**Affected Files:**
- `templates/campaigns.html` (Lines 71-79): Empty JavaScript functions

**Fix Required:**
```javascript
// Replace lines 71-79 in campaigns.html
function toggleCampaign(campaignId) {
    fetch(`/api/campaigns/${campaignId}/toggle`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.reload();
        }
    });
}

function editCampaign(campaignId) {
    window.location.href = `/campaigns/${campaignId}/edit`;
}
```

**Add to `main.py`:**
```python
@main_bp.route('/api/campaigns/<int:campaign_id>/toggle', methods=['POST'])
@login_required
def toggle_campaign(campaign_id):
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=current_user.id).first()
    if campaign:
        campaign.is_active = not campaign.is_active
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Campaign not found'}), 404
```

---

### **TICKET-010: Complete Social OAuth Implementation**
**Status:** DISABLED - "Coming Soon" buttons
**Issue:** OAuth flow exists but not connected to UI

**Affected Files:**
- `templates/settings.html` (Lines 124-125): Buttons disabled
- `auth.py`: Missing OAuth callback routes

**Add to `auth.py`:**
```python
@auth_bp.route('/oauth/instagram/callback')
def instagram_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    # Implement token exchange
    # Store in SocialAccount model
    pass

@auth_bp.route('/oauth/facebook/callback')
def facebook_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    # Implement token exchange
    pass
```

---

### **TICKET-011: Fix Missing Celery Task**
**Status:** BROKEN - Referenced task doesn't exist
**Issue:** Task called but not defined

**Affected File:**
- `tasks/generation.py` (Line 185): Calls `send_weekly_posts_email.delay()`
- Task not defined in any file

**Add to `tasks/generation.py` or create `tasks/email.py`:**
```python
@current_app.task
def send_weekly_posts_email(user_id: int, weekly_gen_id: int):
    """Send email notification about weekly posts"""
    # Implementation provided in original code lines 317-372
    pass
```

---

## 🟢 LOW PRIORITY

### **TICKET-012: Fix Import Issues**
**Status:** MISSING IMPORTS
**Issue:** Missing imports in several files

**Affected Files:**
1. `tasks/monitoring.py` (Line 3): Missing `from tasks.celery_app import celery`
2. `main.py` (Line 1): Missing `from flask import request`

---

### **TICKET-013: Add Error Handling for Missing Config**
**Status:** FRAGILE - No validation for required config
**Issue:** App crashes if environment variables missing

**Affected Files:**
- `config.py`: No validation for required keys
- `app.py` (Line 45): No check for mail config

---

### **TICKET-014: Fix Mobile Navigation**
**Status:** INCOMPLETE - Mobile toggle exists but CSS missing
**Issue:** Sidebar doesn't properly show/hide on mobile

**Affected Files:**
- `static/css/style.css` (Lines 346-367): Mobile styles incomplete
- `static/js/main.js` (Lines 1-12): Toggle function needs refinement

---

## 📊 Summary by File

### **Files That Need Creation:**
- `templates/posts.html` - Post approval interface
- `migrations/` - Database migration scripts

### **Files With Critical Issues:**
- `utils.py` - Duplicate code (Lines 90-178)
- `models.py` - Missing model definitions
- `main.py` - Missing routes and handlers

### **Files With Medium Issues:**
- `services/ai_service.py` - Duplicate method (Lines 400-490)
- `templates/campaigns.html` - Empty JavaScript functions
- `templates/media_library.html` - Placeholder images

## 🎯 Recommended Fix Order

1. **Fix utils.py** (5 min) - Remove duplicates
2. **Add missing models** (10 min) - Prevent import errors
3. **Add core routes** (30 min) - Fix navigation
4. **Create posts.html** (1 hour) - Core functionality
5. **Implement upload backend** (2 hours) - Core feature
6. **Fix media display** (30 min) - User experience
7. Continue with remaining tickets...🚨 CRITICAL PRIORITY (Application Breaking)
TICKET-001: Fix Duplicate Code in utils.py
Status: BROKEN - File contains duplicate content
Issue: Entire file content is duplicated, causing syntax errors
Affected Files:

utils.py (Lines 1-89 duplicated at lines 90-178)

Action Items:

Remove duplicate code starting at line 90
Keep only one version of each function
Test email sending functionality

Code Reference:
