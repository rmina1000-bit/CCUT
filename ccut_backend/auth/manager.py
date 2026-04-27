class UserManager:
    def __init__(self):
        self.current_user = {"id": "CCUT_PRO", "name": "Global Director", "role": "ADMIN", "status": "PRO"}

    def upgrade_to_pro(self):
        self.current_user["status"] = "PRO"
        return True

    def login_with_google(self):
        return self.current_user

user_manager = UserManager()
