import argparse
import getpass

from app.main import Session, User, audit, password_hasher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('username')
    parser.add_argument('--role', choices=['admin', 'analyst', 'viewer'], default='admin')
    parser.add_argument('--reset-password', action='store_true')
    parser.add_argument('--disable', action='store_true')
    args = parser.parse_args()
    if args.disable and args.reset_password:
        raise SystemExit('Choose one action')
    password = None
    if not args.disable:
        password = getpass.getpass('Password: ')
        if len(password) < 12:
            raise SystemExit('Password must be at least 12 characters')
    with Session.begin() as db:
        user = db.get(User, args.username)
        if args.disable:
            if user is None:
                raise SystemExit('User not found')
            user.active = False
            action = 'disable_user'
        elif args.reset_password:
            if user is None:
                raise SystemExit('User not found')
            user.password_hash = password_hasher.hash(password)
            user.active = True
            action = 'reset_password'
        else:
            if user is not None:
                raise SystemExit('User already exists')
            db.add(User(username=args.username, password_hash=password_hasher.hash(password),
                        role=args.role, active=True))
            action = 'create_user'
    audit('system', action, args.username)
    print(f'{action}: {args.username}')


if __name__ == '__main__':
    main()
