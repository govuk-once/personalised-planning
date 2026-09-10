interface HeadingProps {
  heading: string;
  description?: string;
}

export default function Heading(props: Readonly<HeadingProps>) {
  return (
    <>
      <h1>{props.heading}</h1>
      
      { props.description &&
        <p>{props.description}</p>
      }
    </>
  )
}
