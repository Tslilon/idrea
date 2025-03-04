from flask import Flask, request

app = Flask(__name__)

@app.route('/sms', methods=['POST'])
def receive_sms():
    message_body = request.values.get('Body', None)
    from_number = request.values.get('From', None)
    print(f"Message received: {message_body} from {from_number}")
    return "SMS Received"

if __name__ == "__main__":
    app.run(debug=True)