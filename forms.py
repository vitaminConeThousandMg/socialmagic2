from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms.fields import MultipleFileField
from wtforms import StringField, PasswordField, TextAreaField, SelectField, BooleanField, SubmitField, IntegerField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField('Confirm Password', 
                             validators=[DataRequired(), EqualTo('password')])
    brand_name = StringField('Brand Name', validators=[Optional(), Length(max=100)])
    submit = SubmitField('Sign Up')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class BusinessProfileForm(FlaskForm):
    brand_name = StringField('Brand Name', validators=[Optional(), Length(max=100)])
    brand_description = TextAreaField('Brand Description', validators=[Optional()], 
                                    render_kw={"rows": 3, "placeholder": "Brief description of your brand..."})
    brand_voice = TextAreaField('Brand Voice', validators=[Optional()], 
                               render_kw={"rows": 4, "placeholder": "Describe your brand's tone and personality..."})
    brand_style = TextAreaField('Visual Style', validators=[Optional()], 
                               render_kw={"rows": 3, "placeholder": "Describe your preferred visual style..."})
    target_audience = StringField('Target Audience', validators=[Optional(), Length(max=200)],
                                 render_kw={"placeholder": "e.g., Young professionals, fitness enthusiasts"})
    industry = StringField('Industry', validators=[Optional(), Length(max=100)],
                          render_kw={"placeholder": "e.g., Fashion, Technology, Food"})
    ai_instructions = TextAreaField('AI Instructions', validators=[Optional()],
                                   render_kw={"rows": 6, "placeholder": "Custom instructions for AI content generation..."})
    submit = SubmitField('Update Profile')

class CampaignForm(FlaskForm):
    # Campaign name for organization
    name = StringField('Campaign Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional()],
                               render_kw={"rows": 3, "placeholder": "What is this campaign about?"})
    # This is the key field - the prompt template that defines the campaign's content strategy
    prompt_template = TextAreaField('Content Prompt', validators=[DataRequired()],
                                   render_kw={"rows": 6, "placeholder": "Describe the type of content you want to generate..."})
    # How many posts this campaign should generate weekly
    posts_per_week = IntegerField('Posts Per Week', validators=[DataRequired()], default=7)
    submit = SubmitField('Create Campaign')

class BrandAssetForm(FlaskForm):
    name = StringField('Asset Name', validators=[DataRequired(), Length(max=200)])
    asset_type = SelectField('Asset Type', choices=[
        ('logo', 'Logo'),
        ('image', 'Brand Image'),
        ('style_guide', 'Style Guide')
    ], validators=[DataRequired()])
    file = FileField('Upload File', validators=[
        FileRequired(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'pdf', 'svg'], 'Images, PDFs, and SVGs only!')
    ])
    description = TextAreaField('Description', validators=[Optional()],
                               render_kw={"rows": 3, "placeholder": "How should this asset be used?"})
    submit = SubmitField('Upload Asset')

class FileUploadForm(FlaskForm):
    """Form for uploading media files"""
    files = FileField('Upload Files', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'mp4', 'mov', 'avi'], 
                   'Only images (JPG, PNG, GIF) and videos (MP4, MOV, AVI) are allowed!')
    ])
    submit = SubmitField('Upload Files')
