# views.py
from django.http import HttpResponse
from api.telephony.views import run_query

def empty_view(request):
    html_content = """
    <html>
        <head>
            <title>Nothing Here</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background-color: #f0f0f0;
                }
                .container {
                    text-align: center;
                    background-color: #fff;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                }
                h1 {
                    color: #333;
                }
                p {
                    color: #666;
                    font-size: 18px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Here's a Joke for You:</h1>
                <p>Why don't skeletons fight each other?</p>
                <p>Because they don't have the guts!</p>
            </div>
        </body>
    </html>
    """
    return HttpResponse(html_content)



