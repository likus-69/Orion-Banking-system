user_data = {
    "user_1": {
        "x": 75005750990694,
        "y": "Mary Garcia",
        "balance": 1000.00
    },
    "user_2": {
        "x": 48291038475912,
        "y": "John Smith",
        "balance": 10000.00
    },
    "user_3": {
        "x": 91823746501923,
        "y": "Amina Uwase",
        "balance": 5000.00
    },
    "user_4": {
        "x": 37192847561029,
        "y": "David Lee",
        "balance":0.05
    },
    "user_5": {
        "x": 65410293847516,
        "y": "Grace Namubiru",
        "balance": 1500.00
    }
}

print("Welcome to Orion Banking Inc.\nYour Trusted online secure Banking service.")
inup=int(input("\nSign In or Sign Up(1/0): "))

if inup == 1: # Assuming this is your choice variable
    print("Input your a/c info: ")
    x = input("Account number: ")
    y = input("User name: ")
    
    login_successful = False
    

    for user_key, details in user_data.items():
        if details["y"] == y and str(details["x"]) == x:
            login_successful = True
            break
            
    if login_successful:
        print("Successful Login")
        print(f"Welcome {y} to your secure access tunnel.")
    else:
        print("Login Failed.")
else:
    print("Come tomorrow.")
