// src/pages/Checkout.jsx
import { useState, useEffect, useContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import styled from 'styled-components';
import AuthContext from '../context/AuthContext';
import { FaMapMarkerAlt, FaLock, FaCheckCircle, FaExclamationCircle, FaPhoneAlt, FaShieldAlt, FaArrowLeft, FaBoxOpen, FaGift } from 'react-icons/fa';
import { toast } from "react-hot-toast";
import { useNavigate, Link } from 'react-router-dom';
import { SkeletonRow } from '../components/SkeletonLoader';
import { PageHeader, GlowingPageContainer } from '../styles/SharedPageStyles';
import AppLayout from '../components/AppLayout';
import { formatINR } from '../utils/currency';
import { loadRazorpay } from '../utils/loadRazorpay'; 

const Checkout = () => {
  const { axiosInstance, user } = useContext(AuthContext);
  const navigate = useNavigate();

  const [cartItems, setCartItems] = useState([]);
  const [addresses, setAddresses] = useState([]);
  const [selectedAddressId, setSelectedAddressId] = useState(null);
  const [contactPhone, setContactPhone] = useState('');

  const [loading, setLoading] = useState(false);
  const [useWallet, setUseWallet] = useState(false);
  const [isFetching, setIsFetching] = useState(true);

  useEffect(() => {
    if (!user) {
      toast.error("Please login to checkout.");
      navigate('/login');
      return;
    }

    const fetchCheckoutData = async () => {
      setIsFetching(true);
      try {
        const cartRes = await axiosInstance.get('/api/cart-items/');
        setCartItems(cartRes.data);

        const profileRes = await axiosInstance.get(`/api/users/${user.id}/`);
        if (profileRes.data.phone) {
          setContactPhone(profileRes.data.phone);
        }

        const addrRes = await axiosInstance.get('/api/addresses/');
        setAddresses(addrRes.data);

        const defaultAddr = addrRes.data.find(a => a.is_default);
        if (defaultAddr) setSelectedAddressId(defaultAddr.id);
        else if (addrRes.data.length > 0) setSelectedAddressId(addrRes.data[0].id);

      } catch (err) {
        toast.error('❌ Failed to load checkout data');
      } finally {
        setIsFetching(false);
      }
    };

    fetchCheckoutData();
  }, [axiosInstance, user, navigate]);


  const handlePlaceOrder = async () => {
    if (!selectedAddressId) return toast.error('⚠️ Please select a delivery address!');
    if (!contactPhone.trim()) return toast.error('⚠️ A contact phone number is compulsory!');
    if (cartItems.length === 0) return toast.error('⚠️ Your cart is empty!');

    const isRazorpayLoaded = await loadRazorpay();
    if (!isRazorpayLoaded) {
      toast.error('❌ Razorpay SDK failed to load. Disable adblockers for localhost.');
      return;
    }
    
    setLoading(true);
    try {
      const selectedAddr = addresses.find(a => a.id === selectedAddressId);
      const addressSnapshot = `${selectedAddr.label}: ${selectedAddr.full_address}`;
      const payloadTotalPrice = cartTotal.toFixed(2);
      const payloadOrderItems = cartItems.map(item => ({
        product: item.product?.id || item.product,
        quantity: item.quantity,
        price: Number(item.price),
      }));
  
      const orderRes = await axiosInstance.post('/api/orders/create-razorpay-order/', {
        shipping_address: addressSnapshot,
        contact_phone: contactPhone,
        total_price: payloadTotalPrice,
        use_wallet: useWallet,
        order_items: payloadOrderItems,
      });
  
      const orderData = orderRes.data;

      // 🚀 SCENARIO B: FULLY COVERED BY WALLET (BYPASS RAZORPAY)
      if (orderData.payment_complete) {
        toast.success('🎉 Order fully paid using Wallet Balance!');
        setLoading(false);
        navigate(`/order-success/${orderData.order_id}`, {
          state: {
            order: { total_price: payloadTotalPrice },
            payment: orderData.payment,
            userAddress: addressSnapshot,
            userPhone: contactPhone
          }
        });
        return; 
      }
  
      // 🚀 SCENARIO A: PARTIAL OR NO GIFT CARD (PROCEED TO RAZORPAY)
      const options = {
        key: orderData.key_id,
        amount: orderData.amount,
        currency: orderData.currency,
        name: "EazyShop",
        description: "Secure Order Checkout",
        order_id: orderData.razorpay_order_id,
        handler: async function (response) {
          let timeoutHandle;
          
          // 45-Second Safety Timeout Guard
          const safetyTimeout = new Promise((_, reject) => {
              timeoutHandle = setTimeout(() => {
                  reject(new Error("Gateway response timed out. Please check your order history."));
              }, 45000);
          });
          
          try {
            const verifyCall = axiosInstance.post('/api/orders/verify-razorpay-payment/', {
              order_id: orderData.order_id,
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
  
            // Race the API call against the timeout
            const verifyRes = await Promise.race([verifyCall, safetyTimeout]);
            clearTimeout(timeoutHandle);
  
            if (verifyRes.data.success) {
              toast.success('📦 Payment verified & Order placed successfully!');
              navigate(`/order-success/${verifyRes.data.order_id}`, {
                state: {
                  order: { total_price: payloadTotalPrice },
                  payment: verifyRes.data.payment,
                  userAddress: addressSnapshot,
                  userPhone: contactPhone
                }
              });
            } else {
              toast.error('❌ Payment verification failed');
              setLoading(false);
            }
          } catch (err) {
            clearTimeout(timeoutHandle);
            console.error('Verification error:', err);
            toast.error(err.message || '❌ Error verifying payment with server');
            setLoading(false);
          }
        },
        prefill: {
          name: user?.username || "Customer",
          email: user?.email || "",
          contact: contactPhone,
        },
        theme: {
          color: "#0B8457"
        },
        modal: {
          ondismiss: async function() {
            setLoading(false);
            toast("Payment cancelled by user", { icon: '⚠️' });
            
            try {
              await axiosInstance.post(`/api/orders/${orderData.order_id}/cancel/`);
            } catch (cancelErr) {
              console.error('Failed to cancel abandoned order:', cancelErr);
            }
          }
        }
      };
  
      const rzp = new window.Razorpay(options);
      
      rzp.on('payment.failed', function (response) {
        console.warn("Payment failed at gateway:", response.error.description);
      });
  
      rzp.open();
  
    } catch (err) {
      const serverMsg = err.response?.data?.message || err.response?.data?.detail || 'Failed to initialize payment';
      toast.error(`❌ ${serverMsg}`);
      setLoading(false);
    }
  };

  const cartTotal = cartItems.reduce((sum, item) => sum + item.quantity * Number(item.price), 0);
  const walletBalance = Number(user?.wallet_balance || 0);
  const appliedWalletAmount = useWallet ? Math.min(cartTotal, walletBalance) : 0;
  const finalTotal = Math.max(0, cartTotal - appliedWalletAmount);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 300, damping: 24 } }
  };

  if (cartItems.length === 0 && !isFetching) {
    return (
      <AppLayout>
        <GlowingPageContainer $maxWidth="1100px">
          <CheckoutContainer>
            <EmptyState initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
              <span className="emoji">🛒</span>
              <h3>Checkout Unavailable</h3>
              <p>Your cart is currently empty. Add some items to proceed.</p>
              <Link to="/products" className="action-btn"><FaArrowLeft /> Back to Store</Link>
            </EmptyState>
          </CheckoutContainer>
        </GlowingPageContainer>
      </AppLayout>
    );
  }

  return (
    <>
      <AnimatePresence>
        {loading && (
          <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ModalBox initial={{ scale: 0.9, opacity: 0, y: 20 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0, y: -20 }} transition={{ type: "spring", stiffness: 300, damping: 25 }}>
              <IconWrapper>
                <Ring animate={{ rotate: 360 }} transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }} />
                <FaLock size={26} color="#0B8457" />
              </IconWrapper>
              <h2>Processing securely...</h2>
              <h4>256-BIT ENCRYPTION</h4>
              <p>Please do not close this window or refresh your browser while we prepare your transaction.</p>
              <ProgressBarContainer>
                <ProgressFill initial={{ width: "0%" }} animate={{ width: "100%" }} transition={{ duration: 2.4, ease: "easeInOut" }} />
              </ProgressBarContainer>
            </ModalBox>
          </Overlay>
        )}
      </AnimatePresence>

      <AppLayout>
        <GlowingPageContainer $maxWidth="1100px">
          <CheckoutContainer>
            <PageHeader initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: "easeOut" }}>
              <BadgeTag><FaShieldAlt /> 256-bit Encryption</BadgeTag>
              <h1>Secure Checkout</h1>
              <p>Review your details and complete your order.</p>
            </PageHeader>

            {isFetching ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                <SkeletonRow style={{ height: '200px', borderRadius: '24px' }} />
                <SkeletonRow style={{ height: '250px', borderRadius: '24px' }} />
              </div>
            ) : (
              <ContentGrid as={motion.div} variants={containerVariants} initial="hidden" animate="visible">
                <GlassSection variants={itemVariants}>
                  <SectionHeader><FaBoxOpen color="#0B8457" /> Order Summary</SectionHeader>
                  <CartItems>
                    {cartItems.map(item => (
                      <CartItem key={item.id}>
                        <ProductImage>
                          {item.product_image ? <img src={item.product_image} alt={item.product_name} /> : <div className="placeholder" />}
                        </ProductImage>
                        <div className="details">
                          <ProductName>{item.product_name}</ProductName>
                          <ProductQty>Qty: {item.quantity} <span>•</span> {formatINR(item.price)} each</ProductQty>
                        </div>
                        <ItemTotal>{formatINR((item.quantity * Number(item.price)))}</ItemTotal>
                      </CartItem>
                    ))}
                  </CartItems>
                </GlassSection>

                {/* 🚀 NEW: Wallet Application Section */}
                <GlassSection variants={itemVariants}>
                  <SectionHeader><FaGift color="#0B8457" /> EazyShop Wallet</SectionHeader>
                  <GiftCardWrapper>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', background: '#F8FAFC', borderRadius: '12px', border: '1px solid #E2E8F0' }}>
                      <div>
                        <strong style={{ display: 'block', fontSize: '1.1rem', color: '#0F172A', marginBottom: '0.3rem' }}>Available Balance: {formatINR(walletBalance)}</strong>
                        <p style={{ margin: 0, fontSize: '0.9rem', color: '#64748B' }}>Use your unified wallet balance to pay for this order.</p>
                      </div>
                      <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: '0.5rem' }}>
                        <input 
                          type="checkbox" 
                          checked={useWallet} 
                          onChange={(e) => setUseWallet(e.target.checked)} 
                          disabled={walletBalance <= 0}
                          style={{ width: '20px', height: '20px', accentColor: '#0B8457', cursor: walletBalance > 0 ? 'pointer' : 'not-allowed' }}
                        />
                        <span style={{ fontWeight: '700', color: walletBalance > 0 ? '#0B8457' : '#94A3B8' }}>Use Wallet</span>
                      </label>
                    </div>
                  </GiftCardWrapper>
                </GlassSection>

                <GlassSection variants={itemVariants}>
                  <SectionHeader><FaMapMarkerAlt color="#0B8457" /> Delivery Details</SectionHeader>

                  {addresses.length === 0 ? (
                    <WarningBox>
                      <FaExclamationCircle size={24} />
                      <div>
                        <strong>No addresses found</strong>
                        <p>Please go to your <Link to="/dashboard">Dashboard</Link> to add a delivery address.</p>
                      </div>
                    </WarningBox>
                  ) : (
                    <AddressGrid>
                      {addresses.map(addr => (
                        <AddressCard key={addr.id} $selected={selectedAddressId === addr.id} onClick={() => setSelectedAddressId(addr.id)} whileHover={{ y: -4 }} whileTap={{ scale: 0.98 }}>
                          <AnimatePresence>
                            {selectedAddressId === addr.id && (
                              <SelectedBadge initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }} transition={{ type: 'spring', stiffness: 400, damping: 25 }}>
                                <FaCheckCircle />
                              </SelectedBadge>
                            )}
                          </AnimatePresence>

                          <div className="card-header">
                            <div className="icon-box"><FaMapMarkerAlt /></div>
                            <div className="label-row">
                              <strong>{addr.label}</strong>
                              {addr.is_default && <span className="default-pill">Default</span>}
                            </div>
                          </div>
                          <p className="address-text">{addr.full_address}</p>
                        </AddressCard>
                      ))}
                    </AddressGrid>
                  )}

                  <ContactInputWrapper>
                    <div className="label-container">
                      <label><FaPhoneAlt color="#0B8457" /> Delivery Contact Number</label>
                      <span className="verified-badge"><FaLock size={10} /> Verified</span>
                    </div>
                    <LockedField>
                      <FaLock className="lock-icon" />
                      {contactPhone || 'No verified phone number linked'}
                    </LockedField>
                    <p className="helper-text">This number is pulled securely from your verified account profile.</p>
                  </ContactInputWrapper>
                </GlassSection>

                {/* 🚀 UPGRADED: Dynamic Total Section */}
                <TotalSection variants={itemVariants}>
                  <SummaryRow>
                    <span>Cart Total</span>
                    <span>{formatINR(cartTotal)}</span>
                  </SummaryRow>
                  
                  {useWallet && appliedWalletAmount > 0 && (
                    <SummaryRow className="discount">
                      <span>Wallet Applied</span>
                      <span>- {formatINR(appliedWalletAmount)}</span>
                    </SummaryRow>
                  )}

                  <div className="total-row" style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid rgba(0,0,0,0.1)' }}>
                    <span>Total to Pay</span>
                    <TotalAmount>{formatINR(finalTotal)}</TotalAmount>
                  </div>
                  
                  <PlaceOrderButton onClick={handlePlaceOrder} disabled={loading || cartItems.length === 0 || addresses.length === 0 || !contactPhone} whileHover={{ scale: loading || cartItems.length === 0 || addresses.length === 0 || !contactPhone ? 1 : 1.02 }} whileTap={{ scale: loading || cartItems.length === 0 || addresses.length === 0 || !contactPhone ? 1 : 0.98 }}>
                    {loading ? 'Processing...' : (finalTotal > 0 ? 'Place Secure Order' : 'Complete Order with Wallet Balance')}
                  </PlaceOrderButton>
                </TotalSection>
              </ContentGrid>
            )}
          </CheckoutContainer>
        </GlowingPageContainer>
      </AppLayout>
    </>
  );
};

export default Checkout;

const CheckoutContainer = styled.div`
  position: relative; z-index: 1; max-width: 800px; margin: 0 auto; padding: 0 1.5rem;
  @media (max-width: 768px) { padding: 0 0.5rem; }
`;

const BadgeTag = styled.span`
  display: inline-flex; align-items: center; gap: 0.4rem; background: rgba(11, 132, 87, 0.1); color: #0B8457;
  font-size: 0.8rem; font-weight: 700; padding: 0.4rem 1rem; border-radius: 50px; text-transform: uppercase;
  letter-spacing: 1px; margin-bottom: 1rem; border: 1px solid rgba(11, 132, 87, 0.2);
`;

const ContentGrid = styled(motion.div)`
  display: flex; flex-direction: column; gap: 2rem;
  @media (max-width: 768px) { gap: 1.25rem; }
`;

const GlassSection = styled(motion.section)`
  background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  border-radius: 24px; padding: 2rem; border: 1px solid rgba(11, 132, 87, 0.12); box-shadow: 0 10px 40px -10px rgba(0,0,0,0.05);
  @media (max-width: 768px) { padding: 1.25rem; background: rgba(255, 255, 255, 0.75); }
`;

const SectionHeader = styled.h2`
  display: flex; align-items: center; gap: 0.8rem; font-size: 1.4rem; font-weight: 800; color: #0F172A;
  margin-top: 0; margin-bottom: 1.5rem; border-bottom: 1px solid rgba(0, 0, 0, 0.05); padding-bottom: 1rem;
  @media (max-width: 768px) { font-size: 1.15rem; margin-bottom: 1rem; }
`;

const CartItems = styled.div` display: flex; flex-direction: column; gap: 1rem; `;

const CartItem = styled.div`
  display: flex; align-items: center; gap: 1.5rem; padding: 1rem; background: #ffffff;
  border: 1px solid #F1F5F9; border-radius: 16px; transition: background 0.2s;
  &:hover { background: #F8FAFC; }
  .details { flex: 1; min-width: 0; }
  @media (max-width: 768px) { gap: 0.75rem; padding: 0.75rem; }
`;

const ProductImage = styled.div`
  width: 70px; height: 70px; flex-shrink: 0; border-radius: 12px; background: #F1F5F9;
  display: flex; align-items: center; justify-content: center; overflow: hidden; padding: 0.5rem;
  img { width: 100%; height: 100%; object-fit: contain; mix-blend-mode: multiply; }
  .placeholder { width: 100%; height: 100%; background: #E2E8F0; }
  @media (max-width: 768px) { width: 60px; height: 60px; padding: 0.25rem; }
`;

const ProductName = styled.div`
  font-weight: 700; color: #0F172A; font-size: 1.05rem; margin-bottom: 0.3rem; word-wrap: break-word;
  @media (max-width: 768px) { font-size: 0.95rem; }
`;

const ProductQty = styled.div`
  font-size: 0.9rem; color: #64748B; font-weight: 500;
  span { margin: 0 0.4rem; color: #CBD5E1; }
  @media (max-width: 768px) { font-size: 0.8rem; }
`;

const ItemTotal = styled.div`
  margin-left: auto; font-weight: 800; color: #0B8457; font-size: 1.15rem;
  @media (max-width: 768px) { font-size: 1rem; }
`;

const GiftCardWrapper = styled.div`
  .input-group {
    display: flex; gap: 1rem;
    
    input {
      flex: 1; padding: 1rem 1.2rem; border-radius: 12px; border: 1px solid #E2E8F0;
      font-family: monospace; font-size: 1rem; outline: none; transition: all 0.2s; background: #ffffff; color: #0F172A;
    }
    input:focus { border-color: #0B8457; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); }
    input:disabled { background: #F8FAFC; color: #94A3B8; }
    
    button { padding: 0 2rem; border-radius: 12px; font-weight: 700; font-size: 1rem; cursor: pointer; transition: all 0.2s; border: none; }
    .apply-btn { background: #0F172A; color: white; }
    .apply-btn:hover { background: #1E293B; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.2); }
    .remove-btn { background: #FEF2F2; color: #EF4444; border: 1px solid #FECACA; }
    .remove-btn:hover { background: #FEE2E2; }
  }
  
  .applied-success {
    display: flex; align-items: center; gap: 0.5rem; color: #059669; font-weight: 600; font-size: 0.9rem;
    margin-top: 1rem; padding: 0.8rem 1rem; background: #ECFDF5; border-radius: 12px; border: 1px solid #A7F3D0;
  }
  
  @media (max-width: 600px) {
    .input-group { flex-direction: column; }
    .input-group button { padding: 1rem; }
  }
`;

const AddressGrid = styled.div`
  display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.25rem;
  @media (max-width: 768px) { grid-template-columns: 1fr; gap: 1rem; }
`;

const AddressCard = styled(motion.div)`
  position: relative; background: ${props => props.$selected ? 'rgba(11, 132, 87, 0.04)' : '#ffffff'};
  border: 2px solid ${props => props.$selected ? '#0B8457' : '#E2E8F0'}; border-radius: 16px; padding: 1.5rem;
  cursor: pointer; transition: all 0.2s ease; overflow: hidden;
  &:hover { border-color: ${props => props.$selected ? '#0B8457' : '#CBD5E1'}; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.05); }
  .card-header {
    display: flex; align-items: center; gap: 0.8rem; margin-bottom: 1rem;
    .icon-box {
      width: 36px; height: 36px; border-radius: 10px; background: ${props => props.$selected ? '#0B8457' : '#F1F5F9'};
      color: ${props => props.$selected ? '#ffffff' : '#64748B'}; display: flex; align-items: center; justify-content: center;
    }
    .label-row {
      display: flex; align-items: center; gap: 0.5rem;
      strong { color: #0F172A; font-size: 1.05rem; }
      .default-pill { background: #E2E8F0; color: #334155; font-size: 0.7rem; padding: 0.2rem 0.6rem; border-radius: 50px; text-transform: uppercase; font-weight: 800; }
    }
  }
  .address-text { color: #475569; line-height: 1.6; margin: 0; font-size: 0.95rem; }
  @media (max-width: 768px) { padding: 1.25rem; }
`;

const SelectedBadge = styled(motion.div)`
  position: absolute; top: 1rem; right: 1rem; color: #0B8457; font-size: 1.4rem;
  background: #ffffff; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 8px rgba(11, 132, 87, 0.2);
`;

const ContactInputWrapper = styled.div`
  margin-top: 2rem; padding-top: 1.5rem; border-top: 1px dashed rgba(0, 0, 0, 0.1);
  .label-container {
    display: flex; align-items: center; justify-content: space-between; max-width: 100%; margin-bottom: 0.8rem;
    label { display: flex; align-items: center; gap: 0.5rem; font-weight: 700; color: #334155; font-size: 0.95rem; }
    .verified-badge {
      display: flex; align-items: center; gap: 0.3rem; background: #ECFDF5; color: #059669;
      font-size: 0.75rem; font-weight: 800; padding: 0.2rem 0.6rem; border-radius: 50px; text-transform: uppercase;
    }
  }
  .helper-text { font-size: 0.85rem; color: #94A3B8; margin-top: 0.6rem; display: block; }
`;

const LockedField = styled.div`
  width: 100%; max-width: 100%; box-sizing: border-box; padding: 1rem 1.2rem; background: #F8FAFC;
  border: 1px solid #E2E8F0; border-radius: 12px; font-size: 1.05rem; color: #64748B; font-weight: 600;
  display: flex; align-items: center; gap: 0.8rem; cursor: not-allowed; user-select: none; overflow: hidden; word-wrap: break-word;
  .lock-icon { color: #94A3B8; flex-shrink: 0; }
`;

const TotalSection = styled(GlassSection)`
  padding: 2rem;
  .total-row {
    display: flex; justify-content: space-between; align-items: center;
    span:first-child { font-size: 1.2rem; font-weight: 800; color: #0F172A; }
  }
  @media (max-width: 768px) { padding: 1.5rem 1rem; }
`;

const SummaryRow = styled.div`
  display: flex; justify-content: space-between; margin-bottom: 0.8rem; color: #64748B; font-weight: 600; font-size: 1.05rem;
  &.discount { color: #059669; font-weight: 700; }
`;

const TotalAmount = styled.div`
  font-size: 2.2rem; font-weight: 900; color: #0F172A; letter-spacing: -1px;
  @media (max-width: 768px) { font-size: 1.8rem; }
`;

const PlaceOrderButton = styled(motion.button)`
  width: 100%; padding: 1.2rem; background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%);
  color: #ffffff; border: none; border-radius: 16px; font-weight: 800; font-size: 1.15rem; cursor: pointer;
  box-shadow: 0 6px 20px rgba(11, 132, 87, 0.25); transition: all 0.3s ease; margin-top: 1.5rem;
  &:hover:not(:disabled) { box-shadow: 0 8px 25px rgba(11, 132, 87, 0.4); }
  &:disabled { background: #CBD5E1; box-shadow: none; cursor: not-allowed; }
`;

const WarningBox = styled.div`
  display: flex; align-items: center; gap: 1rem; background: #FEF3C7; color: #B45309; padding: 1.5rem; border-radius: 16px; border: 1px solid #FDE68A;
  strong { display: block; font-size: 1.05rem; margin-bottom: 0.2rem; }
  p { margin: 0; font-size: 0.95rem; }
  a { color: #92400E; font-weight: 700; text-decoration: underline; }
`;

const EmptyState = styled(motion.div)`
  text-align: center; padding: 6rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1; margin-top: 2rem;
  .emoji { font-size: 4rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.8rem; font-weight: 900; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1.1rem; margin-bottom: 2rem; }
  .action-btn { display: inline-flex; align-items: center; gap: 0.5rem; background: #0B8457; color: white; text-decoration: none; padding: 0.9rem 2rem; border-radius: 50px; font-weight: 700; transition: all 0.2s ease; box-shadow: 0 4px 14px rgba(11, 132, 87, 0.2); }
`;

const Overlay = styled(motion.div)`
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 1rem;
`;

const ModalBox = styled(motion.div)`
  background: rgba(255, 255, 255, 0.95); padding: 3rem 2rem; border-radius: 24px; text-align: center; max-width: 420px; width: 100%; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
  h2 { color: #0F172A; font-size: 1.5rem; margin: 1.5rem 0 0.4rem 0; font-weight: 900; }
  h4 { color: #0B8457; font-size: 0.85rem; margin: 0 0 1.5rem 0; font-weight: 800; letter-spacing: 1px; }
  p { color: #475569; font-size: 0.95rem; line-height: 1.6; margin-bottom: 2rem; }
`;

const IconWrapper = styled.div`
  position: relative; width: 80px; height: 80px; margin: 0 auto; display: flex; align-items: center; justify-content: center; background: #ECFDF5; border-radius: 50%; box-shadow: 0 0 0 8px rgba(16, 185, 129, 0.1);
`;

const Ring = styled(motion.div)`
  position: absolute; inset: -4px; border: 3px solid transparent; border-top-color: #10B981; border-right-color: #10B981; border-radius: 50%;
`;

const ProgressBarContainer = styled.div` width: 100%; height: 6px; background: #E2E8F0; border-radius: 10px; overflow: hidden; `;
const ProgressFill = styled(motion.div)` height: 100%; background: linear-gradient(90deg, #10B981, #0B8457); border-radius: 10px; `;