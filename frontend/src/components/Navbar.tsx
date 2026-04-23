import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="navbar">
      <Link href="/" className="navbar-brand">
        <span className="brand-icon">🎥</span>
        VideoSync
      </Link>
      <div className="navbar-links">
        <Link href="/" className="nav-link">Dashboard</Link>
        <Link href="/sessions" className="nav-link">Sessions</Link>
        <Link href="/camera" className="nav-link">Camera</Link>
        <Link href="/live" className="nav-link">Live</Link>
      </div>
    </nav>
  );
}
