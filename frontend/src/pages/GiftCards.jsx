// src/pages/GiftCards.jsx
import React, { useState, useContext } from 'react';
import { AuthContext } from '../context/AuthContext';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import { FaGift, FaCheckCircle, FaRupeeSign, FaCopy, FaShieldAlt, FaWallet } from 'react-icons/fa';
import { toast } from 'react-hot-toast';
import { loadRazorpay } from '../utils/loadRazorpay';
import { formatINR } from '../utils/currency';
import AppLayout from '../components/AppLayout';

const PRESET_AMOUNTS = [500, 1000, 2000, 5000];

const GiftCards = () => {
    const { axiosInstance, user, setUser, syncWalletBalance, refreshUser } = useContext(AuthContext); 
    const [amount, setAmount] = useState('');
    const [loading, setLoading] = useState(false);
    const [isVerifying, setIsVerifying] = useState(false);
    const [isRedeeming, setIsRedeeming] = useState(false);
    const [giftCard, setGiftCard] = useState(null);
    const [redeemedBalance, setRedeemedBalance] = useState(null);

    const handlePurchase = async (e) => {
        e.preventDefault();

        const isRazorpayLoaded = await loadRazorpay();
        if (!isRazorpayLoaded) {
            alert('Razorpay SDK failed to load. Disable adblockers for localhost.');
            return;
        }

        setLoading(true);

        try {
            const res = await axiosInstance.post('/api/gift-cards/purchase/', { amount });

            const { order_id, amount: rzpAmount, key } = res.data;

            const options = {
                key: key,
                amount: rzpAmount * 100,
                currency: "INR",
                name: "EazyShop Enterprise",
                description: `Digital Gift Card - ${formatINR(rzpAmount)}`,
                order_id: order_id,
                handler: async function (response) {
                    setIsVerifying(true);
                    try {
                        const verifyRes = await axiosInstance.post('/api/gift-cards/verify/', {
                            razorpay_payment_id: response.razorpay_payment_id,
                            razorpay_order_id: response.razorpay_order_id,
                            razorpay_signature: response.razorpay_signature,
                            amount: rzpAmount
                        });
                        setGiftCard(verifyRes.data);
                    } catch (err) {
                        alert('Payment verification failed. Please contact support.');
                    } finally {
                        setIsVerifying(false);
                    }
                },
                theme: { color: "#0B8457" }
            };

            if (!key) {
                alert('Missing Razorpay Key. Please check backend configuration.');
                setLoading(false);
                return;
            }
            const rzp = new window.Razorpay(options);
            rzp.open();
        } catch (err) {
            console.error(err);
            alert('Failed to initialize payment. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    // 🚀 UPGRADED: Instant Redeem Logic with Robust Production State Synchronization
    const handleInstantRedeem = async () => {
        setIsRedeeming(true);
        try {
            const res = await axiosInstance.post('/api/gift-cards/redeem/', { gift_card_id: giftCard.gift_card_id });
            const newBalance = res.data.new_balance;

            // 1. Instantly sync state across context and broadcast to other tabs
            if (syncWalletBalance && user) {
                syncWalletBalance(user.id, newBalance);
            } else if (setUser && user) {
                setUser(prev => {
                    const updatedUser = { ...prev, wallet_balance: newBalance };
                    localStorage.setItem('user', JSON.stringify(updatedUser));
                    return updatedUser;
                });
            }

            // 2. Guarantee fresh DB sync on production environments
            if (typeof refreshUser === 'function') {
                await refreshUser();
            }
            
            // 3. Trigger the success modal
            setRedeemedBalance(newBalance);
        } catch (err) {
            toast.error(err.response?.data?.error || 'Failed to redeem gift card');
        } finally {
            setIsRedeeming(false);
        }
    };

    const resetFlow = () => {
        setGiftCard(null);
        setAmount('');
        setRedeemedBalance(null);
    };

  return (
      <AppLayout>
        <PageWrapper>
            <GreenOrbTop />
            <GreenOrbBottom />

            {/* 🚀 Gorgeous Redeem Success Modal */}
            <AnimatePresence>
                {redeemedBalance !== null && (
                    <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                        <ModalBox 
                            initial={{ scale: 0.9, y: 20 }} 
                            animate={{ scale: 1, y: 0 }} 
                            exit={{ scale: 0.9, y: 20 }}
                            style={{ 
                                background: 'rgba(255, 255, 255, 0.9)', 
                                backdropFilter: 'blur(25px)', 
                                border: '1px solid rgba(16, 185, 129, 0.3)' 
                            }}
                        >
                            <IconWrapper style={{ background: 'linear-gradient(135deg, #10B981 0%, #0B8457 100%)', color: 'white', border: '4px solid #ECFDF5' }}>
                                <FaCheckCircle size={32} />
                            </IconWrapper>
                            <h2 style={{ color: '#0F172A', marginTop: '1.5rem' }}>Added to Wallet!</h2>
                            <p style={{ fontSize: '1rem', color: '#64748B', marginBottom: '1.5rem' }}>
                                Your gift card value has been successfully transferred to your EazyShop account.
                            </p>
                            
                            <BalanceDisplay>
                                <span>Updated Wallet Balance</span>
                                <strong>{formatINR(redeemedBalance)}</strong>
                            </BalanceDisplay>

                            <PrimaryButton onClick={resetFlow} style={{ marginTop: '0.5rem' }}>
                                Awesome, Thanks!
                            </PrimaryButton>
                        </ModalBox>
                    </Overlay>
                )}
            </AnimatePresence>

            <AnimatePresence>
                {isVerifying && (
                    <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                        <ModalBox initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
                            <IconWrapper>
                                <FaShieldAlt size={32} color="#10B981" />
                                <Ring animate={{ rotate: 360 }} transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }} />
                            </IconWrapper>
                            <h2>Verifying Payment</h2>
                            <h4>DO NOT CLOSE WINDOW</h4>
                            <p>Generating Secure Gift Card... Please do not close this window.</p>
                            <ProgressBarContainer>
                                <ProgressFill initial={{ width: "0%" }} animate={{ width: "100%" }} transition={{ duration: 2, repeat: Infinity }} />
                            </ProgressBarContainer>
                        </ModalBox>
                    </Overlay>
                )}
            </AnimatePresence>

            <GlassContainer
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease: "easeOut" }}
            >
                <Header>
                    <IconWrapper>
                        <FaGift size={28} />
                    </IconWrapper>
                    <h1>Send a Digital Gift Card</h1>
                    <p>The perfect gift, delivered instantly. Redeemable across our entire store.</p>
                </Header>

                <AnimatePresence mode="wait">
                    {giftCard ? (
                        <SuccessState
                            key="success"
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.9 }}
                        >
                            <SuccessHeader>
                                <FaCheckCircle size={40} color="#10B981" />
                                <h2>Payment Successful!</h2>
                                <p>Your digital gift card is ready to use.</p>
                            </SuccessHeader>

                            <PhysicalCardMockup>
                                <CardBrand>EazyShop<span>.</span></CardBrand>
                                <CardValue>{formatINR(amount)}</CardValue>
                                <CardId>
                                    ID: {giftCard.gift_card_id}
                                    <FaCopy
                                      style={{ marginLeft: '10px', cursor: 'pointer', color: '#CBD5E1', transition: 'color 0.2s' }}
                                      onMouseEnter={(e) => e.currentTarget.style.color = '#ffffff'}
                                      onMouseLeave={(e) => e.currentTarget.style.color = '#CBD5E1'}
                                      onClick={() => {
                                        navigator.clipboard.writeText(giftCard.gift_card_id);
                                        toast.success("ID Copied!");
                                      }}
                                    />
                                </CardId>
                                {giftCard.qr_url && (
                                    <QRContainer>
                                        <img src={giftCard.qr_url} alt="Gift Card QR" />
                                    </QRContainer>
                                )}
                            </PhysicalCardMockup>

                            <ButtonGroup>
                                <PrimaryButton onClick={handleInstantRedeem} disabled={isRedeeming}>
                                    <FaWallet style={{ marginRight: '8px' }} />
                                    {isRedeeming ? 'Adding to Wallet...' : 'Instantly Add to My Wallet'}
                                </PrimaryButton>
                                
                                <SecondaryButton onClick={resetFlow}>
                                    Purchase Another Card
                                </SecondaryButton>
                            </ButtonGroup>
                        </SuccessState>
                    ) : (
                        <FormState
                            key="form"
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 20 }}
                            onSubmit={handlePurchase}
                        >
                            <SectionTitle>Select an Amount</SectionTitle>
                            <PresetGrid>
                                {PRESET_AMOUNTS.map(preset => (
                                    <PresetChip
                                        key={preset}
                                        type="button"
                                        $active={Number(amount) === preset}
                                        onClick={() => setAmount(preset)}
                                        whileHover={{ scale: 1.05 }}
                                        whileTap={{ scale: 0.95 }}
                                    >
                                        {formatINR(preset)}
                                    </PresetChip>
                                ))}
                            </PresetGrid>

                            <Divider><span>OR ENTER CUSTOM AMOUNT</span></Divider>

                            <InputWrapper>
                                <FaRupeeSign className="currency-icon" />
                                <CustomInput
                                    type="number"
                                    min="100"
                                    max="50000"
                                    value={amount}
                                    onChange={(e) => setAmount(e.target.value)}
                                    placeholder="Enter amount (Min ₹100)"
                                    required
                                />
                            </InputWrapper>

                            <PrimaryButton
                                type="submit"
                                disabled={loading || !amount || amount < 100}
                                whileHover={{ scale: loading || !amount || amount < 100 ? 1 : 1.02 }}
                                whileTap={{ scale: loading || !amount || amount < 100 ? 1 : 0.98 }}
                            >
                                {loading ? 'Initializing Secure Payment...' : `Secure Checkout - ${amount ? formatINR(amount) : '₹0.00'}`}
                            </PrimaryButton>

                            <SecureBadge>
                                🔒 Payments are 100% secure and encrypted by Razorpay
                            </SecureBadge>
                        </FormState>
                    )}
                </AnimatePresence>
            </GlassContainer>
      </PageWrapper>
      </AppLayout>
    );
};

export default GiftCards;

// ==========================================
// ENTERPRISE STYLED COMPONENTS
// ==========================================

const PageWrapper = styled.div`
    min-height: 75vh; 
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem 1.5rem;
    position: relative;
    overflow: hidden;
    background: transparent; 
`;

const GreenOrbTop = styled.div`
    position: absolute;
    top: -10%;
    left: -5%;
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba(16, 185, 129, 0.45) 0%, transparent 70%);
    border-radius: 50%;
    pointer-events: none;
    z-index: 0;
    filter: blur(40px);
`;

const GreenOrbBottom = styled.div`
    position: absolute;
    bottom: -15%;
    right: -5%;
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba(11, 132, 87, 0.40) 0%, transparent 70%);
    border-radius: 50%;
    pointer-events: none;
    z-index: 0;
    filter: blur(50px);
`;

const GlassContainer = styled(motion.div)`
    position: relative;
    z-index: 1;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-radius: 32px;
    border: 1px solid rgba(11, 132, 87, 0.15);
    box-shadow: 0 25px 50px -12px rgba(15, 23, 42, 0.1);
    width: 100%;
    max-width: 540px;
    padding: 3rem;
    box-sizing: border-box;

    @media (max-width: 600px) {
        padding: 2rem 1.5rem;
        border-radius: 24px;
    }
`;

const Header = styled.div`
    text-align: center;
    margin-bottom: 2.5rem;

    h1 {
        font-size: 2rem;
        font-weight: 800;
        color: #0F172A;
        margin: 1rem 0 0.5rem 0;
    }

    p {
        color: #64748B;
        font-size: 1rem;
        line-height: 1.5;
        margin: 0;
    }
`;

const IconWrapper = styled.div`
    width: 64px;
    height: 64px;
    margin: 0 auto;
    background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
    color: #0B8457;
    border-radius: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 8px 16px rgba(11, 132, 87, 0.1);
    transform: rotate(-5deg);
`;

const FormState = styled(motion.form)`
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
`;

const SectionTitle = styled.label`
    font-size: 0.95rem;
    font-weight: 700;
    color: #334155;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: -0.5rem;
`;

const PresetGrid = styled.div`
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
`;

const PresetChip = styled(motion.button)`
    padding: 1rem;
    background: ${props => props.$active ? '#0B8457' : '#ffffff'};
    color: ${props => props.$active ? '#ffffff' : '#0F172A'};
    border: 2px solid ${props => props.$active ? '#0B8457' : '#E2E8F0'};
    border-radius: 16px;
    font-size: 1.1rem;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: ${props => props.$active ? '0 8px 16px rgba(11, 132, 87, 0.2)' : 'none'};

    &:hover {
        border-color: #0B8457;
        color: ${props => props.$active ? '#ffffff' : '#0B8457'};
    }
`;

const Divider = styled.div`
    display: flex;
    align-items: center;
    text-align: center;
    color: #94A3B8;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 1px;
    margin: 0.5rem 0;

    &::before, &::after {
        content: '';
        flex: 1;
        border-bottom: 1px dashed #CBD5E1;
    }

    span {
        padding: 0 1rem;
    }
`;

const InputWrapper = styled.div`
    position: relative;
    display: flex;
    align-items: center;

    .currency-icon {
        position: absolute;
        left: 1.2rem;
        color: #64748B;
        font-size: 1.2rem;
    }
`;

const CustomInput = styled.input`
    width: 100%;
    padding: 1.2rem 1.2rem 1.2rem 3rem;
    font-size: 1.25rem;
    font-weight: 700;
    color: #0F172A;
    background: #ffffff;
    border: 2px solid #E2E8F0;
    border-radius: 16px;
    outline: none;
    transition: all 0.2s;
    box-sizing: border-box;

    &::placeholder {
        color: #94A3B8;
        font-weight: 500;
        font-size: 1.1rem;
    }

    &:focus {
        border-color: #0B8457;
        box-shadow: 0 0 0 4px rgba(11, 132, 87, 0.1);
    }

    &::-webkit-outer-spin-button,
    &::-webkit-inner-spin-button {
        -webkit-appearance: none;
        margin: 0;
    }
    -moz-appearance: textfield;
`;

const ButtonGroup = styled.div`
    display: flex;
    flex-direction: column;
    gap: 1rem;
    width: 100%;
    margin-top: 2rem;
`;

const PrimaryButton = styled(motion.button)`
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.2rem;
    background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%);
    color: white;
    font-size: 1.1rem;
    font-weight: 800;
    border: none;
    border-radius: 16px;
    cursor: pointer;
    box-shadow: 0 8px 20px rgba(11, 132, 87, 0.25);

    &:disabled {
        background: #94A3B8;
        box-shadow: none;
        cursor: not-allowed;
        opacity: 0.7;
    }
`;

const SecondaryButton = styled(motion.button)`
    width: 100%;
    padding: 1.2rem;
    background: rgba(11, 132, 87, 0.05);
    color: #0B8457;
    font-size: 1.1rem;
    font-weight: 800;
    border: 2px solid #0B8457;
    border-radius: 16px;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
        background: rgba(11, 132, 87, 0.1);
    }
`;

const SecureBadge = styled.div`
    text-align: center;
    color: #64748B;
    font-size: 0.85rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
`;

const SuccessState = styled(motion.div)`
    display: flex;
    flex-direction: column;
    align-items: center;
`;

const SuccessHeader = styled.div`
    text-align: center;
    margin-bottom: 2rem;

    h2 {
        color: #0F172A;
        font-size: 1.5rem;
        font-weight: 800;
        margin: 1rem 0 0.25rem 0;
    }

    p {
        color: #64748B;
        font-size: 0.95rem;
        margin: 0;
    }
`;

const PhysicalCardMockup = styled.div`
    width: 100%;
    max-width: 400px;
    height: 240px;
    background: linear-gradient(135deg, #0B8457 0%, #064E3B 100%);
    border-radius: 24px;
    padding: 2rem;
    box-sizing: border-box;
    position: relative;
    overflow: hidden;
    box-shadow: 0 20px 40px rgba(15, 23, 42, 0.3), inset 0 1px 0 rgba(255,255,255,0.1);
    display: flex;
    flex-direction: column;
    justify-content: space-between;

    &::after {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 60%);
        transform: rotate(30deg);
        pointer-events: none;
    }
`;

const CardBrand = styled.div`
    font-size: 1.5rem;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: -0.5px;

    span {
        color: #10B981;
    }
`;

const CardValue = styled.div`
    font-size: 2.5rem;
    font-weight: 800;
    color: #ffffff;
    text-shadow: 0 2px 10px rgba(0,0,0,0.5);
    margin: 1rem 0;
`;

const CardId = styled.div`
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.9rem;
    color: #CBD5E1;
    letter-spacing: 2px;
    display: flex;
    align-items: center;
    word-break: break-all;
    padding-right: 80px;
`;

const QRContainer = styled.div`
    position: absolute;
    bottom: 1.5rem;
    right: 1.5rem;
    width: 70px;
    height: 70px;
    background: white;
    padding: 6px;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);

    img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        border-radius: 8px;
    }
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

const BalanceDisplay = styled.div`
  background: #F8FAFC;
  padding: 1.5rem;
  border-radius: 16px;
  border: 1px solid #E2E8F0;
  margin: 1.5rem 0;
  
  span {
    display: block;
    color: #64748B;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 0.8rem;
    margin-bottom: 0.5rem;
  }
  
  strong {
    font-size: 2.5rem;
    color: #0F172A;
    font-weight: 900;
    letter-spacing: -1px;
  }
`;

const Ring = styled(motion.div)`
  position: absolute; inset: -4px; border: 3px solid transparent; border-top-color: #10B981; border-right-color: #10B981; border-radius: 50%;
`;

const ProgressBarContainer = styled.div` width: 100%; height: 6px; background: #E2E8F0; border-radius: 10px; overflow: hidden; `;
const ProgressFill = styled(motion.div)` height: 100%; background: linear-gradient(90deg, #10B981, #0B8457); border-radius: 10px; `;