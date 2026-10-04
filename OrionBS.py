# 1. Define your data at the top so Python knows it exists
user_data = {
    "user_1": {
        "x": 75005750990694396,
        "y": "Mary Garcia"
    },
    "user_2": {
        "x": 72688556523041,
        "y": "Robert Hernandez"
    }
}

print("Welcome to Orion Banking Inc.")

# 2. Convert input to an int right away for easy math/comparison
s_in_s_up = int(input("Sign in(1)/ Sign up(0): "))

if s_in_s_up == 1:
    print("\nInput your a/c info ")
    x = int(input("Account number: "))
    y = str(input("User name: "))
    
    # 3. Check the nested dictionary for a match
    account_found = False
    for user, info in user_data.items():
        if info["x"] == x and info["y"].lower() == y.lower():
            # 4. Use an f-string to inject variables into the print statement
            print(f"\nWelcome {info['y']}, Account number {info['x']}")
            account_found = True
            break
            
    if not account_found:
        print("\nInvalid account number or user name.")

elif s_in_s_up == 0:
    print("\nSign up system coming soon!")
    
else:
    print("\nInvalid option selected.")