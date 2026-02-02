# Write It Great - Book Proposal Evaluation System

A self-contained web application for evaluating book proposals using AI. Built with Flask and designed for deployment on Heroku.

## Features

- **AI-Powered Evaluation**: Uses OpenAI GPT-4 to analyze book proposals
- **Three Submission Types**:
  - Full Proposal (all sections evaluated)
  - Marketing Only (only marketing section scored)
  - No Marketing (marketing excluded from scoring)
- **Professional PDF Reports**: Branded feedback reports with detailed scores
- **Team Notifications**: Automatic email alerts to your team via Mailchimp
- **Built-in NDA & Terms**: Authors agree to terms before submission
- **Branded Design**: Matches Write It Great website styling

## Quick Start (Local Development)

```bash
# Clone the repository
git clone <your-repo-url>
cd writeitgreat-proposal-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your API keys

# Run the development server
python app.py
```

Visit `http://localhost:5000` to see the application.

## Heroku Deployment

### Prerequisites
- Heroku account
- Heroku CLI installed
- OpenAI API key
- Mailchimp Transactional (Mandrill) API key (optional, for email notifications)

### Step-by-Step Deployment

1. **Create a new Heroku app**:
   ```bash
   heroku login
   heroku create writeitgreat-proposals
   ```

2. **Set environment variables**:
   ```bash
   heroku config:set OPENAI_API_KEY=sk-your-key-here
   heroku config:set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
   heroku config:set TEAM_EMAIL=team@writeitgreat.com
   
   # Optional: Mailchimp for email notifications
   heroku config:set MAILCHIMP_API_KEY=your-mandrill-api-key
   heroku config:set MAILCHIMP_FROM_EMAIL=proposals@writeitgreat.com
   ```

3. **Deploy**:
   ```bash
   git add .
   git commit -m "Initial deployment"
   git push heroku main
   ```

4. **Verify deployment**:
   ```bash
   heroku open
   heroku logs --tail  # Monitor for any errors
   ```

### Custom Domain (Optional)

To use a custom domain like `proposals.writeitgreat.com`:

1. Add the domain in Heroku:
   ```bash
   heroku domains:add proposals.writeitgreat.com
   ```

2. Get the DNS target:
   ```bash
   heroku domains
   ```

3. Add a CNAME record in your DNS settings pointing to the Heroku DNS target.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |
| `SECRET_KEY` | Yes | Random string for Flask sessions |
| `TEAM_EMAIL` | Yes | Email to receive team notifications |
| `MAILCHIMP_API_KEY` | No | Mandrill API key for email notifications |
| `MAILCHIMP_FROM_EMAIL` | No | From email address for notifications |
| `FLASK_DEBUG` | No | Set to 'true' for development |

## Project Structure

```
writeitgreat-proposal-system/
├── app.py                 # Main Flask application
├── evaluate.py            # OpenAI evaluation logic
├── report_generator.py    # PDF report generation
├── email_service.py       # Mailchimp email integration
├── templates/
│   ├── index.html         # Main submission form
│   ├── results.html       # Evaluation results page
│   └── error.html         # Error page
├── static/
│   ├── css/
│   │   └── style.css      # Branded styles
│   ├── js/
│   │   └── main.js        # Form handling
│   └── images/
│       └── logo.webp      # Write It Great logo
├── requirements.txt       # Python dependencies
├── Procfile              # Heroku process file
├── runtime.txt           # Python version
└── .env.example          # Environment variables template
```

## Scoring System

### Full Proposal Weights
| Category | Weight |
|----------|--------|
| Marketing & Platform | 30% |
| Overview & Concept | 20% |
| Author Credentials | 15% |
| Comparative Titles | 15% |
| Sample Writing | 10% |
| Book Outline | 5% |
| Completeness | 5% |

### Tier Classification
| Tier | Score Range | Description |
|------|-------------|-------------|
| A | 85-100 | Exceptional - Ready for top-tier publishers |
| B | 70-84 | Strong - Minor improvements recommended |
| C | 50-69 | Promising - Significant work needed |
| D | 0-49 | Needs Development - Major revisions required |

## Connecting to Your Wix Site

1. Create a button on your Wix site
2. Link it to your Heroku app URL (e.g., `https://writeitgreat-proposals.herokuapp.com`)
3. Alternatively, embed in an iframe or use Wix's "Connect to External URL" option

## Troubleshooting

### Common Issues

**"OpenAI API error"**
- Verify your API key is correct
- Check your OpenAI account has credits
- Ensure the key has access to GPT-4

**"Could not extract text from PDF"**
- The PDF may be image-based (scanned)
- The PDF may be encrypted/password-protected
- Try a different PDF file

**"Email not sent"**
- Verify Mailchimp/Mandrill API key
- Check the from email is verified
- Review Heroku logs for specific errors

### Viewing Logs
```bash
heroku logs --tail
```

## Cost Estimates

- **Heroku**: ~$7/month (Eco Dyno) or $25/month (Basic)
- **OpenAI**: ~$0.50-$2.00 per evaluation (GPT-4)
- **Mailchimp Transactional**: Free for low volume (<500 emails/month)

For ~20 evaluations/month: **~$20-50/month total**

## Support

For technical issues, contact: hello@writeitgreat.com

---

© 2025 Write It Great LLC. All rights reserved.
