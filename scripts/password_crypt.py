from passlib.context import CryptContext

print("Please Enter the password to encrypt:", end='')
Pass = input()
Pass = CryptContext(schemes=['pbkdf2_sha512']).encrypt(Pass)
print("Encrypted password is:" + Pass)
open('pasword.txt','w').write(Pass)