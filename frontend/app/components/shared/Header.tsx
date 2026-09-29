import styles from "@/app/page.module.css";
import { usePathname } from "next/navigation";
import BackButton from "./BackButton";
import ProfileIconSvg from "@/app/icons/profileIcon";

interface HeaderProps {
  backButtonUrl: string;
  backButtonText: string;
  backButtonGreyVariant?: boolean;
}

export default function Header(props: Readonly<HeaderProps>) {
    const pathname = usePathname();

    return (
        <header className={styles.header}>
            <BackButton
                url={props.backButtonUrl}
                text={props.backButtonText}
                greyVariant={props.backButtonGreyVariant}
            />
            {pathname !== "/end-session" && (
                <a className={styles.profileIconLink} href="/end-session">
                    <ProfileIconSvg />
                </a>
            )}
        </header>
    )
}
