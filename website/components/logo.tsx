import Image from "next/image";
import logo from "@/public/brand/fixelect-logo.png";

/** The Fixelect wordmark, exactly as the app ships it. */
export function Logo({ className, eager = false }: { className?: string; eager?: boolean }) {
  return <Image src={logo} alt="Fixelect" sizes="160px" loading={eager ? "eager" : "lazy"} className={className} />;
}
