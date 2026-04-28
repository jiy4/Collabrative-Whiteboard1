import socket
import threading
import json

HOST = '0.0.0.0'
PORT = 5006

clients = {}
clients_lock = threading.Lock()


def handle_client(client_socket, addr):
    buffer = ''
    try:
        while True:
            data = client_socket.recv(4096).decode('utf-8')
            if not data:
                break
            buffer += data
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if not line:
                    continue
                message = json.loads(line)
                msg_type = message.get("type")
                if msg_type == "join":
                    username = message.get("username", "Anonymous")
                    print(f"Client {addr} connected as {username}")
                    with clients_lock:
                        clients[client_socket] = username
                    broadcast({"type": "join", "username": username})
                elif msg_type in ["draw", "clear", "status", "undo", "redo"]:
                    username = clients.get(client_socket, "Anonymous")
                    message["username"] = username
                    broadcast(message)
    except Exception as e:
        print(f"Error with client {addr}: {e}")
    # finally:
    #     with clients_lock:
    #         username = clients.get(client_socket, "Anonymous")
    #         if client_socket in clients:
    #             del clients[client_socket]
    #             broadcast({"type": "leave", "username": username})
    #     client_socket.close()
    #     print(f"Client {addr} ({username}) disconnected")

    finally:
        with clients_lock:
            username = clients.get(client_socket, "Anonymous")
            if client_socket in clients:
                del clients[client_socket]
        broadcast({"type": "leave", "username": username})  # ← moved OUTSIDE the lock
        client_socket.close()
        print(f"Client {addr} ({username}) disconnected")    


# def broadcast(message):
#     data = json.dumps(message).encode('utf-8') + b'\n'
#     with clients_lock:
#         for client in list(clients.keys()):
#             try:
#                 client.sendall(data)
#             except:
#                 client.close()
#                 del clients[client]
def broadcast(message):
    data = json.dumps(message).encode('utf-8') + b'\n'
    dead_clients = []
    with clients_lock:
        for client in list(clients.keys()):
            try:
                client.sendall(data)
            except:
                dead_clients.append(client)
        for client in dead_clients:
            client.close()
            if client in clients:
                del clients[client]

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"Server started on {HOST}:{PORT}")
    while True:
        client_socket, addr = server.accept()
        threading.Thread(target=handle_client, args=(client_socket, addr), daemon=True).start()


if __name__ == "__main__":
    main()