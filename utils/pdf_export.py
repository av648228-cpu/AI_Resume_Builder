"""PDF rendering helpers based on WeasyPrint."""


def create_pdf(html_content, base_url=None):
    """Render HTML to PDF bytes; the input HTML includes the resume stylesheet.

    The WeasyPrint import is lazy so the HTML editor can still run on a machine
    where native PDF-rendering dependencies have not been installed yet.
    """
    from weasyprint import HTML

    return HTML(string=html_content, base_url=base_url).write_pdf()
