import styles from "@/app/page.module.css";
import Button from "@/app/components/shared/Button";

interface ListCardProps {
  heading?: string;
  headingLevel?: number;
  listItems: Array<string>;
  editable?: boolean;
  greyVariant?: boolean;
  onEdit?: () => void;
}

export default function ListCard(props: Readonly<ListCardProps>) {
  const listCardClassVariant = props.greyVariant ? `${styles.listCard}--grey` : "";

  function headingHtml (headingLevel: number, heading: string) {
    if(headingLevel === 1) {
      return (
        <h1 className={styles.listCardHeading}>{heading}</h1>
      )
    }
    else if(headingLevel === 2) {
      return (
        <h2 className={styles.listCardHeading}>{heading}</h2>
      )
    }
    else {
      return (
        <h3 className={styles.listCardHeading}>{heading}</h3>
      )
    }
  }

  return (
    <div className={`${styles.listCard} ${listCardClassVariant}`}>
      {props.headingLevel && props.heading && (
        <div className={styles.listCardHeadingContainer}>
          { headingHtml(props.headingLevel, props.heading) }
          {props.editable && (
            <Button type={"edit"} text={"Edit"} onClick={props.onEdit ?? (() => {})} />
          )}
        </div>
      )}

      <ul className={styles.listCardList}>
        {props.listItems.map((listItem, index) => (
          <li className={styles.listCardListItem} key={index + 1}>
            {listItem}
          </li>
        ))}
      </ul>
    </div>
  )
}
