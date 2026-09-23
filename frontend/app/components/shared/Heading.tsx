import styles from "@/app/page.module.css";

interface HeadingProps {
  heading: string;
  generating?: boolean;
  description?: string;
}

export default function Heading(props: Readonly<HeadingProps>) {
  return (
    <>
      <h1>
        {props.heading}
        {props.generating && (
          <span className={styles.loadingEllipsis}>...</span>
        )}
      </h1>
      
      { props.description &&
        <p>{props.description}</p>
      }
    </>
  )
}
