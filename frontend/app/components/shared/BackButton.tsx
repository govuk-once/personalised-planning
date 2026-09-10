import styles from "@/app/page.module.css";
import BackSvg from "@/app/icons/back";

interface ButtonProps {
  url: string;
  text: string;
  greyVariant?: boolean;
}

export default function BackButton(props: Readonly<ButtonProps>) {
  const backButtonLinkClassVariant = props.greyVariant ? `${styles.backButtonLink}--grey` : "";

  return (
    <a className={`${styles.backButtonLink} ${backButtonLinkClassVariant}`} href={props.url}>
      <BackSvg />
      <span>{props.text}</span>
    </a>
  )
}
