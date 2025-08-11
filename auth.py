from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, BusinessProfile
from forms import RegistrationForm, LoginForm
from utils import send_verification_email
import stripe

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if user already exists
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user:
            flash('Email already registered. Please sign in instead.', 'error')
            return redirect(url_for('auth.login'))
        
        # Create new user
        user = User(
            email=form.email.data.lower(),
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        db.session.flush()  # Get user ID
        
        # Create business profile
        profile = BusinessProfile(
            user_id=user.id,
            brand_name=form.brand_name.data or ''
        )
        db.session.add(profile)
        db.session.commit()
        
        # Send verification email
        send_verification_email(user)
        
        flash('Registration successful! Please check your email to verify your account.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', form=form)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        
        if user and check_password_hash(user.password_hash, form.password.data):
            if not user.is_verified:
                flash('Please verify your email address before logging in.', 'warning')
                return redirect(url_for('auth.login'))
            
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash('Invalid or expired verification link.', 'error')
        return redirect(url_for('auth.login'))
    
    user.is_verified = True
    user.verification_token = None
    db.session.commit()
    
    flash('Email verified successfully! You can now log in.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/subscription')
@login_required
def subscription():
    if current_user.subscription_active:
        return redirect(url_for('main.dashboard'))
    
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    
    try:
        # Create Stripe customer if doesn't exist
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={'user_id': current_user.id}
            )
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            line_items=[{
                'price': current_app.config['STRIPE_PRICE_ID'],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('auth.subscription_success', _external=True),
            cancel_url=url_for('auth.subscription', _external=True),
        )
        
        return redirect(session.url)
    except Exception as e:
        flash('Error creating subscription. Please try again.', 'error')
        return render_template('auth/subscription.html')

@auth_bp.route('/subscription/success')
@login_required
def subscription_success():
    current_user.subscription_active = True
    db.session.commit()
    flash('Subscription activated! Welcome to SocialMagic Premium.', 'success')
    return redirect(url_for('main.dashboard'))