def format_inr(number):
    """
    Formats a number into Indian Rupee string representation (Lakhs/Crores)
    e.g. 100000.50 -> ₹1,00,000.50
    """
    try:
        num = round(float(number), 2)
        is_negative = num < 0
        num = abs(num)
        num_str = f"{num:.2f}"
        integer_part, decimal_part = num_str.split('.')
        
        last_three = integer_part[-3:]
        other_numbers = integer_part[:-3]
        
        if other_numbers:
            other_numbers = other_numbers[::-1]
            groups = [other_numbers[i:i+2] for i in range(0, len(other_numbers), 2)]
            other_numbers = ','.join(groups)[::-1]
            integer_part = f"{other_numbers},{last_three}"
            
        sign = "-" if is_negative else ""
        return f"{sign}₹{integer_part}.{decimal_part}"
    except (ValueError, TypeError):
        return "₹0.00"
