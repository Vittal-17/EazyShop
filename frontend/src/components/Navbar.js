// src/components/Navbar.jsx
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useContext, useState, useEffect } from 'react';
import AuthContext from '../context/AuthContext';
import { 
  FaHome, FaShoppingCart, FaUser, 
  FaSignInAlt, FaStore, FaClipboardList, 
  FaUserShield, FaSignOutAlt, FaHeart,
  FaChevronDown, FaBars, FaTimes, FaEnvelope,
  FaTruck, FaGift
} from 'react-icons/fa';
import { motion, AnimatePresence } from 'framer-motion';
import styled from 'styled-components';
import { toast } from "react-hot-toast";
import FullScreenSpinner from './FullScreenSpinner';

import brandLogoImg from '../assets/android-chrome-192x192.png';

const Navbar = () => {
  const { user, logoutUser } = useContext(AuthContext);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 10);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (!user) setIsDropdownOpen(false);
  }, [user]);

  useEffect(() => {
    setIsMobileMenuOpen(false);
    setIsDropdownOpen(false);
  }, [location.pathname]);

  const toggleDropdown = () => setIsDropdownOpen(!isDropdownOpen);
  const toggleMobileMenu = () => setIsMobileMenuOpen(!isMobileMenuOpen);

  const handleLogout = () => {
    setIsLoggingOut(true);
    setTimeout(() => {
      logoutUser();
      setIsLoggingOut(false);
      setTimeout(() => {
        toast.success('👋 Logged out securely!', { duration: 3000, id: 'logout-success' });
      }, 250);
    }, 1000);
  };

  const renderNavLinks = () => (
    <>
      <CustomLink to="/" label="Home" icon={<FaHome />} currentPath={location.pathname} />
      <CustomLink to="/products" label="Store" icon={<FaStore />} currentPath={location.pathname} />
      <CustomLink to="/gift-cards" label="Gift Cards" icon={<FaGift />} currentPath={location.pathname} />
      <CustomLink to="/cart" label="Cart" icon={<FaShoppingCart />} currentPath={location.pathname} />
      
      {user && (
        <CustomLink to="/dashboard" label="Dashboard" icon={<FaClipboardList />} currentPath={location.pathname} />
      )}
      
      {user?.role === 'admin' && (
        <CustomLink to="/admin" label="Admin" icon={<FaUserShield />} currentPath={location.pathname} />
      )}
      
      {user?.role === 'seller' && (
        <CustomLink to="/vendor" label="Vendor HQ" icon={<FaTruck />} currentPath={location.pathname} />
      )}
    </>
  );

  return (
    <>
      <AnimatePresence>
        {isLoggingOut && <FullScreenSpinner message="Signing out securely..." />}
      </AnimatePresence>

      <NavContainer 
        $isScrolled={isScrolled}
        initial={{ y: -100 }}
        animate={{ y: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      >
        <NavContent>
          <LeftSection>
            <BrandLogo to="/">
              <img src={brandLogoImg} alt="EazyShop Logo" className="logo-img" />
              EazyShop
            </BrandLogo>
            <DesktopLinks>
              {renderNavLinks()}
            </DesktopLinks>
          </LeftSection>

          <RightSection>
            {user ? (
              <>
                <DesktopWishlist>
                  <CustomLink to="/wishlist" label="Wishlist" icon={<FaHeart />} currentPath={location.pathname} />
                </DesktopWishlist>
                
                <UserDropdownContainer>
                  <UserButton onClick={toggleDropdown} $isOpen={isDropdownOpen}>
                    {/* 🚀 CLOUDINARY PROFILE PICTURE INTEGRATION IN NAVBAR */}
                    <NavAvatarWrapper>
                      {user?.profile_picture ? (
                        <img src={user.profile_picture} alt={user.username || 'User'} />
                      ) : user?.username ? (
                        <span>{user.username.charAt(0).toUpperCase()}</span>
                      ) : (
                        <FaUser className="user-icon" />
                      )}
                    </NavAvatarWrapper>

                    <UsernameText>{user.username}</UsernameText> 
                    <motion.div animate={{ rotate: isDropdownOpen ? 180 : 0 }}>
                      <FaChevronDown size={12} />
                    </motion.div>
                  </UserButton>
                  
                  <AnimatePresence>
                    {isDropdownOpen && (
                      <DropdownMenu
                        initial={{ opacity: 0, y: 15, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 10, scale: 0.95 }}
                        transition={{ duration: 0.2, ease: "easeOut" }}
                      >
                        <UserInfo>
                          <UserInfoHeader>
                            <NavAvatarWrapper style={{ width: '38px', height: '38px', fontSize: '1rem' }}>
                              {user?.profile_picture ? (
                                <img src={user.profile_picture} alt={user.username || 'User'} />
                              ) : user?.username ? (
                                <span>{user.username.charAt(0).toUpperCase()}</span>
                              ) : (
                                <FaUser />
                              )}
                            </NavAvatarWrapper>
                            <UserInfoText>
                              <span className="username">{user.username}</span>
                              <span className="email"><FaEnvelope size={11} /> {user.email}</span>
                            </UserInfoText>
                          </UserInfoHeader>
                        </UserInfo>
                        
                        <DropdownButton onClick={() => navigate('/dashboard')}>
                          <FaUserShield /> Manage Profile
                        </DropdownButton>
                        
                        <DropdownDivider />
                        <LogoutButton onClick={handleLogout}><FaSignOutAlt /> Logout</LogoutButton>
                      </DropdownMenu>
                    )}
                  </AnimatePresence>
                </UserDropdownContainer>
              </>
            ) : (
              <DesktopWishlist>
                <CustomLink to="/login" label="Login" icon={<FaSignInAlt />} currentPath={location.pathname} />
              </DesktopWishlist>
            )}

            <MobileToggleButton onClick={toggleMobileMenu}>
              {isMobileMenuOpen ? <FaTimes size={22} /> : <FaBars size={22} />}
            </MobileToggleButton>
          </RightSection>
        </NavContent>

        {/* Floating Mobile Menu */}
        <AnimatePresence>
          {isMobileMenuOpen && (
            <MobileMenuContainer
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
            >
              <MobileLinksWrapper>
                {renderNavLinks()}
                {user ? (
                  <CustomLink to="/wishlist" label="Wishlist" icon={<FaHeart />} currentPath={location.pathname} />
                ) : (
                  <CustomLink to="/login" label="Login" icon={<FaSignInAlt />} currentPath={location.pathname} />
                )}
              </MobileLinksWrapper>
            </MobileMenuContainer>
          )}
        </AnimatePresence>
      </NavContainer>
    </>
  );
};

// ==========================================
// COMPONENT HELPERS & STYLED COMPONENTS
// ==========================================

const CustomLink = ({ to, label, icon, currentPath }) => {
  const isActive = currentPath === to;
  return (
    <NavLink 
      to={to} 
      $isActive={isActive}
      whileHover={{ scale: 1.05 }} 
      whileTap={{ scale: 0.95 }}
    >
      {icon} <span className="label">{label}</span>
    </NavLink>
  );
};

// 🚀 UPGRADED FLOATING NAVBAR
const NavContainer = styled(motion.div)`
  position: fixed;
  top: 16px;
  left: 0;
  right: 0;
  margin: 0 auto;
  width: calc(100% - 2.5rem);
  max-width: 1450px;
  min-height: 68px;
  border-radius: 24px;
  box-sizing: border-box;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: space-between;
  
  background: ${props => props.$isScrolled ? 'rgba(209, 250, 229, 0.95)' : 'rgba(220, 252, 231, 0.9)'};
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(11, 132, 87, 0.22);
  box-shadow: ${props => props.$isScrolled ? '0 15px 40px -10px rgba(11, 132, 87, 0.25)' : '0 10px 30px rgba(11, 132, 87, 0.1)'};
  transition: background 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;

  @media (max-width: 768px) {
    top: 10px;
    width: calc(100% - 1rem);
    min-height: 58px;
    border-radius: 18px;
    padding: 0 0.75rem;
  }
`;

const NavContent = styled.div`
  display: flex;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  align-items: center;
  justify-content: space-between;
  padding: 0 2rem;
  
  @media (max-width: 768px) { padding: 0 1rem; }
`;

const LeftSection = styled.div`
  display: flex;
  align-items: center;
  gap: 2rem;
`;

const BrandLogo = styled(Link)`
  font-size: 1.5rem;
  font-weight: 800;
  color: #0B8457;
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  letter-spacing: -0.5px;
  
  .logo-img {
    height: 38px;
    width: auto;
    object-fit: contain;
    border-radius: 50%;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.8), 0 4px 12px rgba(11, 132, 87, 0.3);
    transition: transform 0.3s ease;
  }

  &:hover .logo-img {
    transform: scale(1.05) rotate(-5deg);
  }
`;

const DesktopLinks = styled.div`
  display: none;
  @media (min-width: 900px) { display: flex; gap: 0.5rem; align-items: center; }
`;

const RightSection = styled.div`
  display: flex;
  gap: 1rem;
  align-items: center;
`;

const DesktopWishlist = styled.div`
  display: none;
  @media (min-width: 900px) { display: block; }
`;

const NavLink = styled(motion(Link))`
  text-decoration: none;
  font-size: 0.95rem;
  font-weight: 600;
  padding: 0.5rem 1rem;
  border-radius: 50px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: ${props => props.$isActive ? '#ffffff' : '#4B5563'};
  background: ${props => props.$isActive ? '#0B8457' : 'transparent'};
  transition: all 0.2s ease-in-out;
  
  svg {
    font-size: 1.1rem;
  }

  &:hover {
    color: ${props => props.$isActive ? '#ffffff' : '#0B8457'};
    background: ${props => props.$isActive ? '#0B8457' : 'rgba(11, 132, 87, 0.08)'};
  }
`;

const UserDropdownContainer = styled.div` position: relative; `;

/* 🚀 NAVBAR AVATAR WRAPPER COMPONENT */
const NavAvatarWrapper = styled.div`
  width: 30px;
  height: 30px;
  border-radius: 50%;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%);
  color: white;
  font-size: 0.85rem;
  font-weight: 800;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(11, 132, 87, 0.25);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
`;

const UserButton = styled(motion.button)`
  background: ${props => props.$isOpen ? 'rgba(11, 132, 87, 0.08)' : 'transparent'};
  border: 1px solid ${props => props.$isOpen ? 'rgba(11, 132, 87, 0.2)' : 'transparent'};
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: #0B8457;
  cursor: pointer;
  padding: 0.35rem 0.8rem;
  border-radius: 50px;
  transition: all 0.2s ease;

  .user-icon { font-size: 1.05rem; }

  &:hover { background: rgba(11, 132, 87, 0.08); }

  @media (max-width: 768px) {
    padding: 0.25rem 0.5rem;
    font-size: 0.85rem;
    gap: 0.3rem;
  }
`;

const UsernameText = styled.span`
  max-width: 100px; 
  white-space: nowrap; 
  overflow: hidden; 
  text-overflow: ellipsis;

  @media (max-width: 480px) {
    display: none; 
  }

  @media (min-width: 481px) and (max-width: 768px) {
    max-width: 75px;
  }
`;

const DropdownMenu = styled(motion.div)`
  position: absolute;
  right: 0;
  top: calc(100% + 1rem);
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 20px;
  box-shadow: 0 15px 40px rgba(0, 0, 0, 0.12);
  width: 280px;
  padding: 1.25rem;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  box-sizing: border-box;

  @media (max-width: 768px) {
    position: fixed; 
    top: 85px; 
    left: 0;
    right: 0;
    margin: 0 auto; 
    width: 92vw; 
    max-width: 340px; 
  }
`;

const UserInfo = styled.div`
  display: flex;
  flex-direction: column;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #F1F5F9;
  margin-bottom: 0.25px;
`;

const UserInfoHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.8rem;
  width: 100%;
`;

const UserInfoText = styled.div`
  display: flex;
  flex-direction: column;
  overflow: hidden;
  width: calc(100% - 46px);

  .username {
    color: #0F172A;
    font-size: 1rem;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .email {
    color: #64748B;
    font-size: 0.82rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
`;

const DropdownButton = styled(motion.button)`
  background: #f3f4f6;
  border: none;
  padding: 0.8rem;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 0.95rem;
  font-weight: 600;
  color: #374151;
  margin-top: 0.5rem;
  
  &:hover { background: #e5e7eb; color: #111827; }
  svg { color: #0B8457; }
`;

const DropdownDivider = styled.div` height: 1px; background: rgba(0,0,0,0.05); margin: 0.5rem 0; `;

const LogoutButton = styled(motion.button)`
  color: white;
  background: #0B8457;
  border: none;
  font-size: 0.95rem;
  font-weight: 600;
  padding: 0.8rem;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  cursor: pointer;
  transition: all 0.2s ease;
  
  &:hover { background: #096b46; }
`;

const MobileToggleButton = styled.button`
  display: flex; background: none; border: none; color: #0B8457; cursor: pointer; padding: 0.5rem;
  @media (min-width: 900px) { display: none; }
`;

const MobileMenuContainer = styled(motion.div)`
  width: 100%;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(11, 132, 87, 0.15);
  border-radius: 24px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.15);
  position: absolute;
  top: calc(100% + 15px);
  left: 0;
  @media (min-width: 900px) { display: none; }
`;

const MobileLinksWrapper = styled.div`
  display: flex;
  flex-direction: column;
  padding: 1.5rem;
  gap: 0.75rem;
`;

export default Navbar;