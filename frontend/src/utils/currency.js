export const formatINR = (amount) => {
    const num = Number(amount);
    if (isNaN(num)) return "₹0.00";
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(num);
};
