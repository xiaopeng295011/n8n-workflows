# IVD Email Digest Templates

This directory contains Jinja2 templates for generating daily email digests from the IVD monitor database.

## Templates

### `ivd_digest.html`

Responsive HTML email template with:

- **Inline CSS** - Email client compatible styling (Outlook, Apple Mail, Gmail)
- **Table-based layout** - Maximum compatibility across email clients
- **UTF-8 encoding** - Full support for Simplified Chinese characters
- **Mobile responsive** - Adapts to viewport width using media queries
- **Category sections** - Records grouped by category with visual hierarchy
- **Company grouping** - Within each category, records are organized by company
- **Metadata display** - Source, publish date, summary, and call-to-action links
- **Failed source warnings** - Optional display of ingestion errors

### `ivd_digest.txt`

Plain text fallback template with:

- Clean hierarchical structure matching HTML version
- Category and company organization preserved
- Full Chinese character support
- Suitable for text-only email clients

## Template Variables

Both templates expect the following variables:

### Required Variables

- `digest_date` (str) - Date in YYYY-MM-DD format
- `subject` (str) - Email subject line
- `intro_text` (str) - Introductory paragraph
- `categories` (dict) - Organized record data structure
- `total_count` (int) - Total number of records
- `category_count` (int) - Number of categories with records
- `company_count` (int) - Number of unique companies
- `generated_at` (str) - Timestamp when digest was generated

### Optional Variables

- `failed_sources` (list) - List of source names that failed to fetch data

## Category Structure

The `categories` dictionary has this structure:

```python
{
    "category_key": {
        "display_name": "Category Name 中文名称",
        "count": 5,
        "records_by_company": {
            "Company A": [
                {
                    "id": 123,
                    "title": "Record Title",
                    "summary": "Record summary...",
                    "url": "https://...",
                    "source": "Source Name",
                    "publish_date": "2024-01-15"
                },
                ...
            ],
            "Company B": [...],
            ...
        }
    },
    ...
}
```

## Category Order

Categories appear in priority order:

1. NHSA Policy 医保政策 (`nhsa_policy`)
2. NHC Policy 卫健委政策 (`nhc_policy`)
3. Financial Reports 财报资讯 (`financial_reports`)
4. Product Launches 产品上市 (`product_launches`)
5. Bidding & Tendering 招标采购 (`bidding_tendering`)
6. Industry Media 行业媒体 (`industry_media`)
7. Other Updates 其他动态 (`unknown`)

## Usage

Templates are automatically loaded by `EmailDigestBuilder`:

```python
from src.ivd_monitor.email_builder import EmailDigestBuilder, DigestConfig

config = DigestConfig(
    subject_format="IVD Daily Digest - {date}",
    intro_text="Your daily IVD intelligence summary."
)

builder = EmailDigestBuilder(config=config)
html_content, text_content = builder.render_digest("2024-01-15")
```

## Email Client Compatibility

### Tested Clients

- ✅ Gmail (Web, Android, iOS)
- ✅ Apple Mail (macOS, iOS)
- ✅ Outlook (2016+, Office 365, Outlook.com)
- ✅ Thunderbird
- ✅ Yahoo Mail

### Compatibility Notes

- **Inline styles only** - No external CSS files
- **Table-based layout** - Grid and flexbox not used
- **Web fonts avoided** - System fonts ensure consistency
- **Image-free** - No external image dependencies
- **Limited gradients** - Background gradients use safe fallbacks

### Best Practices

When sending emails using these templates:

1. Send as `multipart/alternative` with both HTML and plain text parts
2. Set `Content-Type: text/html; charset=utf-8` for HTML part
3. Set proper email headers (`From`, `To`, `Subject`, `Date`)
4. Consider using a dedicated email service (SendGrid, AWS SES, etc.)
5. Test with email preview tools before production deployment

## Customization

To customize templates:

1. Modify color scheme in inline `style` attributes
2. Update category display names in `email_builder.py`
3. Adjust layout spacing and typography
4. Add company logos or branding (test thoroughly with email clients)

## Testing

Run template tests:

```bash
pytest tests/test_ivd_email_builder.py -v
```

Preview locally:

```bash
python -m src.ivd_monitor.email_builder --date 2024-01-15 --format html --output preview.html
```
